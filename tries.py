"""fium try: every attempt at a project's numbers, kept or dropped, and why, so no idea is tried twice blind."""
import json, sys
from fnmatch import fnmatch
from pathlib import Path

from check import git
from compare import globs, runs_dir

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


def try_main(a):
    repo = Path(git(".", "rev-parse", "--show-toplevel").stdout.strip() or ".").resolve()
    rows = read(repo)
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
    bad = judge_changed(repo, rows)
    if bad:
        sys.exit(f"This attempt changes the judge: {', '.join(bad)}. Revert it; an attempt can't change how it's judged (bench/judge).")
