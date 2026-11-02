"""fium try: every attempt at a project's numbers, kept or dropped, and why, so no idea is tried twice blind."""
import json, sys
from fnmatch import fnmatch
from pathlib import Path

from check import git
from compare import change, globs, inert_globs, runs_dir
from done import base_branch, done

STATUSES = ("keep", "discard", "crash", "retest", "park")
# What judges an attempt: an attempt may add to it (a new scorer checks more) but never change it.
JUDGE = ["bench/*", "test/*", "tests/*", "*noise.json", "*baseline.json"]
STOP_AFTER = 5


def log_path(repo):
    return runs_dir(repo) / "tries.jsonl"


def read(repo):
    p = log_path(repo)
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []


def touched(repo, commit):
    return git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", commit).stdout.split()


def record(repo, idea, status, reason="", **more):
    sha = git(repo, "rev-parse", "HEAD").stdout.strip()
    row = {"commit": sha, "parent": git(repo, "rev-parse", "-q", "--verify", "HEAD~1").stdout.strip() or None,
           "idea": idea, "status": status, "reason": reason, "files": touched(repo, sha), **more}
    log_path(repo).parent.mkdir(parents=True, exist_ok=True)
    with log_path(repo).open("a") as f:
        f.write(json.dumps(row) + "\n")
    return row


def since_keep(rows):
    n = 0
    for r in reversed(rows):
        if r["status"] == "keep":
            break
        n += r["status"] != "retest"
    return n


def changes(repo, rows):
    # What this attempt changed: the tree against the last keep, or HEAD when nothing was kept yet.
    keeps = [r["commit"] for r in rows if r["status"] == "keep"]
    out = git(repo, "diff", "--name-status", "--no-renames", keeps[-1] if keeps else "HEAD").stdout.splitlines()
    return [tuple(l.split("\t", 1)) for l in out if "\t" in l]


def judge_changed(repo, rows):
    js = globs(repo, "judge", JUDGE)
    return [f for st, f in changes(repo, rows) if st != "A" and any(fnmatch(f, g) for g in js)]


CUTS = ("loc", "bytes", "count")


def unread(repo, files):
    # Files no measured row reads: inert ones, and those bench/affects.json maps to no task.
    p = Path(repo) / "bench" / "affects.json"
    rules = json.loads(p.read_text())["rules"] if p.exists() else []
    hit = lambda f: next((r["tasks"] for r in rules if any(fnmatch(f, g) for g in r["files"])), None)
    return all(hit(f) == "none" or hit(f) is None and any(fnmatch(f, g) for g in inert_globs(repo)) for f in files)


def moved(res):
    return "; ".join(f"{n}: {change(v.get('base'), v.get('run'))}" for n, v in res["verdicts"].items() if v["verdict"] != "same")


def outcome(repo, res, target, files):
    # The keep rule. A cut (fewer lines, bytes or a count) with nothing worse is kept; an addition must make the
    # target the plan named better. Deleting what nothing measures says nothing is safe, so it's parked.
    vs = res["verdicts"]
    if res["failed"]:
        return "crash", f"{', '.join(res['failed'])} fails now"
    if res["blocked"] or res["hard"] or res["grew"] or res["other_model"]:
        return "discard", moved(res) or "ran on another model"
    if any(v["verdict"] == "inconclusive" for v in vs.values()):
        return "retest", moved(res)
    better = [n for n, v in vs.items() if v["verdict"] == "better"]
    if any(vs[n]["kind"] in CUTS for n in better) or target in better:
        return "keep", moved(res)
    if unread(repo, files):
        return "park", "nothing measured reads " + ", ".join(files)
    return "discard", "nothing got better" + (f" ({target} is {vs[target]['verdict']})" if target in vs else "")


def attempt(repo, rows, a):
    if git(repo, "status", "--porcelain").stdout.strip():
        sys.exit("Commit the attempt first, so it can be measured and reverted.")
    branch = base_branch(repo)
    anchor = git(repo, "merge-base", branch, "HEAD").stdout.strip()
    keeps = [r["commit"] for r in rows if r["status"] == "keep"]
    base = keeps[-1] if keeps else anchor
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    if head == base:
        sys.exit("HEAD is the last keep: commit the attempt first.")
    files = git(repo, "diff", "--name-only", base, "HEAD").stdout.split()
    status, reason = outcome(repo, done(repo, base, branch, a.costly), a.target, files)
    if status == "keep" and anchor != base:
        # Small rises that each pass against the last keep can't add up: the branch is held to where it left main too.
        since = done(repo, anchor, branch, a.costly, print=lambda *_: None)
        if since["blocked"] or since["hard"] or since["grew"]:
            status, reason = "discard", f"since {branch}: {moved(since)}"
    row = record(repo, a.idea, status, reason, target=a.target, base=base)
    print(f"{row['idea']}: {reason}")
    print(status)
    sys.exit(0 if status == "keep" else 1)


def try_main(a):
    repo = Path(git(".", "rev-parse", "--show-toplevel").stdout.strip() or ".").resolve()
    rows = read(repo)
    if judge_changed(repo, rows):
        sys.exit(f"This attempt changes the judge: {', '.join(judge_changed(repo, rows))}. Revert it; an attempt can't change how it's judged (bench/judge).")
    if a.idea and not a.record:
        return attempt(repo, rows, a)
    if a.record:
        row = record(repo, a.idea or "", a.record, a.reason or "")
        return print(f"{row['status']}  {row['commit'][:7]}  {row['idea']}")
    kept = sum(r["status"] == "keep" for r in rows)
    decided = sum(r["status"] in ("keep", "discard", "crash") for r in rows)
    print(f"fium try: {repo.name}, {len(rows)} attempts, {kept} of {decided} kept")
    for r in rows:
        print(f"  {r['status']:<8} {r['commit'][:7]}  {r['idea']}" + (f": {r['reason']}" if r.get("reason") else ""))
    if since_keep(rows) >= STOP_AFTER:
        print(f"{since_keep(rows)} in a row with no keep: stop or change approach.")
    mine = {f for _, f in changes(repo, rows)}
    seen = [r for r in rows if r["status"] in ("discard", "crash", "park") and mine & set(r.get("files", []))]
    if seen:
        print("Dropped before, touching what you changed:")
        for r in seen:
            print(f"  {r['commit'][:7]}  {r['idea']}: {r.get('reason') or r['status']}")
