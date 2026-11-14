"""fium try: every attempt at a project's numbers, kept or dropped, and why, so no idea is tried twice blind."""
import json, sys
from fnmatch import fnmatch
from pathlib import Path

from check import git
from compare import change, globs, runs_dir
import done as done_module
from done import base_branch, done

STATUSES = ("keep", "discard", "crash", "retest", "park", "confirm")
# What judges an attempt: an attempt may add to it (a new scorer checks more) but never change it.
JUDGE = ["bench/*", "test/*", "tests/*", "*noise.json", "*baseline.json"]
STOP_AFTER = 5


def log_path(repo):
    return runs_dir(repo) / "tries.jsonl"


def read(repo):
    p = log_path(repo)
    return [json.loads(l) for l in p.read_text().splitlines() if l.strip()] if p.exists() else []


branch_of = lambda repo: git(repo, "branch", "--show-current").stdout.strip()


def touched(repo, commit):
    return git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", commit).stdout.split()


def record(repo, idea, status, reason="", **more):
    sha = git(repo, "rev-parse", "HEAD").stdout.strip()
    row = {"commit": sha, "parent": git(repo, "rev-parse", "-q", "--verify", "HEAD~1").stdout.strip() or None,
           "branch": branch_of(repo), "idea": idea, "status": status, "reason": reason, "files": touched(repo, sha), **more}
    log_path(repo).parent.mkdir(parents=True, exist_ok=True)
    with log_path(repo).open("a") as f:
        f.write(json.dumps(row) + "\n")
    return row


def since_keep(rows):
    n = 0
    for r in reversed(rows):
        if r["status"] == "keep":
            break
        n += r["status"] not in ("retest", "confirm")
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


def moved(res):
    return "; ".join(f"{n}: {change(v.get('base'), v.get('run'))}" for n, v in res["verdicts"].items() if v["verdict"] != "same")


def outcome(res, target, cut=False):
    # The keep rule. A cut (fewer lines, bytes or a count) with nothing worse is kept; an addition must make the
    # target the plan named better. Deleting what nothing measures says nothing is safe, so it's parked.
    vs = res["verdicts"]
    if res["failed"]:
        return "crash", f"{', '.join(res['failed'])} fails now"
    if res["blocked"] or res["hard"] or res["grew"] or res["other_model"]:
        return "discard", moved(res) or "ran on another model"
    if any(v["verdict"] == "inconclusive" and (v["run"] > v["base"]) == (v.get("dir", "lower") == "lower") for v in vs.values()):
        # Too close to call and moved the wrong way: more reps before anything is decided.
        return "retest", moved(res)
    better = [n for n, v in vs.items() if v["verdict"] == "better"]
    if any(vs[n]["kind"] in CUTS for n in better) or target in better:
        return "keep", moved(res)
    if cut:
        return "park", "it cut what no number measures; measure it or leave it"
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
    size = lambda rev, f: int(git(repo, "cat-file", "-s", f"{rev}:{f}").stdout.strip() or 0)
    cut = sum(size("HEAD", f) - size(base, f) for f in git(repo, "diff", "--name-only", base, "HEAD").stdout.split()) < 0
    res = done(repo, base, branch, a.costly)
    status, reason = outcome(res, a.target, cut)
    if status == "keep" and anchor != base:
        # Small rises that each pass against the last keep can't add up: the branch is held to where it left main too.
        since = done(repo, anchor, branch, print=lambda *_: None)
        if since["blocked"] or since["hard"] or since["grew"]:
            status, reason = "discard", f"since {branch}: {moved(since)}"
    if status == "keep" and res["raw"]:
        # An agent eval's lucky run is how a keep gets picked, so the numbers logged come from fresh reps.
        status = "confirm"
    row = record(repo, a.idea, status, reason, target=a.target, base=base)
    print(f"{row['idea']}: {reason}")
    if status == "confirm":
        print("Measure it again before it counts: fium try --confirm --costly")
    print(status)
    sys.exit(0 if status in ("keep", "confirm") else 1)


def confirm(repo, rows, a):
    head = git(repo, "rev-parse", "HEAD").stdout.strip()
    last = rows[-1] if rows else {}
    if last.get("status") != "confirm" or last.get("commit") != head:
        sys.exit("Nothing to confirm: HEAD isn't an attempt fium try marked confirm.")
    res = done(repo, last["base"], base_branch(repo), True)
    status, reason = outcome(res, last.get("target"))
    if status == "keep":
        cache = runs_dir(repo) / f"done-{head}.raw.json"
        have = json.loads(cache.read_text()) if cache.exists() else {}
        cache.write_text(json.dumps({**have, **{c: {**x, "confirmed": True} for c, x in res["raw"].items() if x["code"] == 0}}))
    else:
        status, reason = "discard", f"didn't hold on fresh reps: {reason}"
    record(repo, last["idea"], status, reason, target=last.get("target"), base=last["base"])
    print(f"{last['idea']}: {reason}")
    print(status)
    sys.exit(0 if status == "keep" else 1)


def try_main(a):
    done_module.TIMEOUT = a.timeout
    repo = Path(git(".", "rev-parse", "--show-toplevel").stdout.strip() or ".").resolve()
    every = read(repo)
    # Every worktree of a repo logs to one file, so each loop reads only the attempts made on its own branch.
    here = branch_of(repo)
    rows = [r for r in every if r.get("branch") == here]
    if judge_changed(repo, rows):
        sys.exit(f"This attempt changes the judge: {', '.join(judge_changed(repo, rows))}. Revert it; an attempt can't change how it's judged (bench/judge).")
    if a.confirm:
        return confirm(repo, rows, a)
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
    # Another loop's drops still teach this one what failed on the same files.
    seen = [r for r in every if r["status"] in ("discard", "crash", "park") and mine & set(r.get("files", []))]
    if seen:
        print("Dropped before, touching what you changed:")
        for r in seen:
            print(f"  {r['commit'][:7]}  {r['idea']}: {r.get('reason') or r['status']}")
