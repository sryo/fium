#!/usr/bin/env python3
"""fium's own bench: what its rules cost an agent to read, how well they're checked, and how fast the checker runs.
Writes a run in the price format (RULES.md K2). Usage: bench/run.py [--reps N] [out.json]"""
import argparse, json, re, subprocess, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIUM = ROOT / "fium"
READ = ["RULES.md", "AGENTS.md", "skills/fium/SKILL.md"]


def git(*a):
    return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True).stdout.strip()


def rule_ids(rules):
    return re.findall(r"^- \*\*([A-Z]\d+)( ✓)?\*\*", rules, re.M)


def untested_checks(rules, tests):
    return sum(1 for rid, tick in rule_ids(rules) if tick and f'"{rid}"' not in tests)


def unnamed_rules(rules):
    # Top-level bullets are rules and need an id; indented ones are sub-points of the rule above.
    return sum(1 for l in rules.splitlines() if l.startswith("- ") and not re.match(r"- \*\*[A-Z]\d+", l))


def wall_ms(cmd, reps, cwd):
    out = []
    for _ in range(reps):
        t = time.perf_counter()
        subprocess.run(cmd, capture_output=True, cwd=cwd)
        out.append(round((time.perf_counter() - t) * 1000, 2))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?")
    ap.add_argument("--reps", type=int, default=7)
    a = ap.parse_args()
    # Stamp first, so the run names the code it measured (K2).
    commit, dirty = git("rev-parse", "HEAD"), bool(git("status", "--porcelain"))
    rules, tests = (ROOT / "RULES.md").read_text(), (ROOT / "test" / "test_check.py").read_text()
    loc = sum(1 for l in FIUM.read_text().splitlines() if l.strip())
    with tempfile.TemporaryDirectory() as t:
        noisy = lambda xs: {"metrics": {"t": {"dir": "lower", "kind": "time", "samples": xs}}}
        Path(t, "b.json").write_text(json.dumps(noisy([100, 101, 99, 100, 102, 98, 100, 101])))
        Path(t, "r.json").write_text(json.dumps(noisy([104, 99, 103, 101, 100, 105, 102, 98])))
        compare = wall_ms([sys.executable, str(FIUM), "price", "compare", "--json", "b.json", "r.json"], a.reps, t)
    m = lambda kind, xs, dir="lower": {"dir": dir, "kind": kind, "samples": xs}
    run = {
        "commit": commit, "dirty": dirty,
        "metrics": {
            "rules": m("count", [len(rule_ids(rules))]),
            "untested_checks": m("count", [untested_checks(rules, tests)]),
            "unnamed_rules": m("count", [unnamed_rules(rules)]),
            "read_bytes": m("bytes", [sum(len((ROOT / p).read_bytes()) for p in READ)]),
            "loc": m("loc", [loc]),
            "check_ms": m("time", wall_ms([sys.executable, str(FIUM), "check", "."], a.reps, ROOT)),
            "compare_ms": m("time", compare),
        },
        "limits": {"untested_checks": 0, "unnamed_rules": 0},
    }
    out = Path(a.out) if a.out else ROOT / "bench" / "runs" / f"{commit[:12]}{'-dirty' if dirty else ''}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(run, indent=1) + "\n")
    print(out)


if __name__ == "__main__":
    main()
