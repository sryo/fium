#!/usr/bin/env python3
"""The turn-end hook replayed on real sessions whose blocks were labelled by hand: how often it sends back a reply it
shouldn't (wrong_blocks), lets through one it should send back (missed_blocks), and how long it takes on the longest.
Labels are {transcript path: [line indexes where it blocks]}, -1 for the session's end. They name the user's sessions,
so they live outside the repo, beside the runs. Usage: bench/hook.py [--labels FILE] [out.json]"""
import argparse, json, os, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from learn import NOT_THE_USER  # noqa: E402
from replycheck import landed_unheard  # noqa: E402


def turn_ends(lines):
    # The hook runs as the agent hands the turn back: just before each thing the user says, and when the session ends.
    ends = []
    for i, line in enumerate(lines):
        try:
            row = json.loads(line)
            m = row.get("message") or {}
        except (ValueError, AttributeError):
            continue
        c = m.get("content")
        text = c if isinstance(c, str) else " ".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text") \
            if isinstance(c, list) else ""
        if i and m.get("role") == "user" and text.strip() and not NOT_THE_USER.match(text) and not row.get("isMeta"):
            ends.append(i)
    return ends + [len(lines)]


def blocks(lines):
    # Sessions from before fium done saved its verdict are replayed with none saved, as they ran.
    return {i for i in turn_ends(lines) if landed_unheard(lines[:i])}


def main():
    home = Path(os.environ.get("FIUM_HOME") or "~/.fium").expanduser()
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?")
    ap.add_argument("--labels", default=str(home / "hook-labels.json"))
    a = ap.parse_args()
    if not Path(a.labels).is_file():
        sys.exit(f"bench/hook.py: no labels at {a.labels}, so nothing to replay.")
    labels = json.loads(Path(a.labels).read_text())
    gone = [f for f in labels if not Path(f).is_file()]
    if gone:
        sys.exit(f"bench/hook.py: labelled sessions are gone, so they'd count as clean: {', '.join(gone)}")
    git = lambda *x: subprocess.run(["git", "-C", str(ROOT), *x], capture_output=True, text=True).stdout.strip()
    commit, dirty = git("rev-parse", "HEAD"), bool(git("status", "--porcelain"))
    wrong = missed = 0
    for f, want in labels.items():
        lines = Path(f).read_text(errors="ignore").splitlines()
        want, got = {len(lines) if i == -1 else i for i in want}, blocks(lines)
        for kind, at in (("wrong", got - want), ("missed", want - got)):
            for i in sorted(at):
                print(f"{kind}: {f} at line {i}", file=sys.stderr)
        wrong, missed = wrong + len(got - want), missed + len(want - got)
    longest = max(labels, key=lambda f: Path(f).stat().st_size)
    lines = Path(longest).read_text(errors="ignore").splitlines()
    ms = []
    for _ in range(5):
        t = time.perf_counter()
        landed_unheard(lines)
        ms.append(round((time.perf_counter() - t) * 1000, 2))
    count = lambda x: {"dir": "lower", "kind": "count", "samples": [x]}
    run = {"commit": commit, "dirty": dirty, "limits": {"wrong_blocks": 0, "missed_blocks": 0},
           "metrics": {"wrong_blocks": count(wrong), "missed_blocks": count(missed), "hook_ms": {"dir": "lower", "kind": "time", "samples": ms}}}
    out = Path(a.out) if a.out else home / "runs" / "fium" / f"{commit[:12]}{'-dirty' if dirty else ''}.hook.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(run, indent=1) + "\n")
    print(out)


if __name__ == "__main__":
    main()
