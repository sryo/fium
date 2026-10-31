#!/usr/bin/env python3
"""fium's own bench: what its rules cost an agent to read, how well they're checked, and how fast the checker runs.
Writes a run in the price format (RULES.md K2). Usage: bench/run.py [--reps N] [--paired [REV]] [out.json]
--paired also measures REV (default: bench/baseline.json's commit), timing both checkers alternately in this
session so machine drift cancels out, and prints the base path, then the run path."""
import argparse, json, re, subprocess, sys, tempfile, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
READ = ["RULES.md", "AGENTS.md", "skills/fium/SKILL.md"]


def git(*a):
    return subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True).stdout.strip()


def reader(rev):
    show = lambda p: subprocess.run(["git", "-C", str(ROOT), "show", f"{rev}:{p}"], capture_output=True, text=True).stdout
    return (lambda p: (ROOT / p).read_text()) if rev is None else show


def rule_ids(rules):
    return re.findall(r"^- \*\*([A-Z]\d+)( ✓)?\*\*", rules, re.M)


def untested_checks(rules, tests):
    return sum(1 for rid, tick in rule_ids(rules) if tick and f'"{rid}"' not in tests)


def unnamed_rules(rules):
    # Top-level bullets are rules and need an id; indented ones are sub-points of the rule above.
    return sum(1 for l in rules.splitlines() if l.startswith("- ") and not re.match(r"- \*\*[A-Z]\d+", l))


def exact(read):
    rules = read("RULES.md")
    m = lambda kind, x: {"dir": "lower", "kind": kind, "samples": [x]}
    return {
        "rules": m("count", len(rule_ids(rules))),
        "untested_checks": m("count", untested_checks(rules, read("test/test_check.py"))),
        "unnamed_rules": m("count", unnamed_rules(rules)),
        "read_bytes": m("bytes", sum(len(read(p).encode()) for p in READ)),
        "loc": m("loc", sum(1 for p in ("fium", "sleep.py") for l in read(p).splitlines() if l.strip())),
    }


def wall_ms(cmd, cwd):
    t = time.perf_counter()
    subprocess.run(cmd, capture_output=True, cwd=cwd)
    return round((time.perf_counter() - t) * 1000, 2)


def timings(fiums, reps):
    # Rep i runs every checker once, in an order that rotates each rep, so drift and order hit them all alike.
    out = [{"check_ms": [], "compare_ms": []} for _ in fiums]
    # A baseline from before compare left `price` still spells it `price compare`.
    compare = [["price", "compare"] if 'add_parser("price"' in Path(f).read_text() else ["compare"] for f in fiums]
    with tempfile.TemporaryDirectory() as t:
        noisy = lambda xs: {"metrics": {"t": {"dir": "lower", "kind": "time", "samples": xs}}}
        Path(t, "b.json").write_text(json.dumps(noisy([100, 101, 99, 100, 102, 98, 100, 101])))
        Path(t, "r.json").write_text(json.dumps(noisy([104, 99, 103, 101, 100, 105, 102, 98])))
        for i in range(reps):
            for j in sorted(range(len(fiums)), key=lambda j: (j + i) % len(fiums)):
                out[j]["check_ms"].append(wall_ms([sys.executable, fiums[j], "check", "."], ROOT))
                out[j]["compare_ms"].append(wall_ms([sys.executable, fiums[j], *compare[j], "--json", "b.json", "r.json"], t))
    return [{k: {"dir": "lower", "kind": "time", "samples": v} for k, v in o.items()} for o in out]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?")
    ap.add_argument("--reps", type=int, default=7)
    ap.add_argument("--paired", nargs="?", const="baseline", metavar="REV")
    a = ap.parse_args()
    # Stamp first, so the run names the code it measured (K2).
    commit, dirty = git("rev-parse", "HEAD"), bool(git("status", "--porcelain"))
    limits = {"untested_checks": 0, "unnamed_rules": 0}
    out = Path(a.out) if a.out else ROOT / "bench" / "runs" / f"{commit[:12]}{'-dirty' if dirty else ''}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    if not a.paired:
        (t,) = timings([str(ROOT / "fium")], a.reps)
        out.write_text(json.dumps({"commit": commit, "dirty": dirty, "metrics": {**exact(reader(None)), **t}, "limits": limits}, indent=1) + "\n")
        return print(out)
    rev = json.loads((ROOT / "bench" / "baseline.json").read_text())["commit"] if a.paired == "baseline" else a.paired
    sha = git("rev-parse", "--verify", "-q", f"{rev}^{{commit}}")
    if not sha:
        sys.exit(f"--paired: {rev!r} is not a commit. Put the output path before --paired, or write --paired=REV.")
    rev = sha
    with tempfile.TemporaryDirectory() as t:
        old = Path(t, "fium")
        old.write_text(reader(rev)("fium"))
        tb, tr = timings([str(old), str(ROOT / "fium")], a.reps)
    base_out = out.with_name(out.stem + ".base.json")
    base_out.write_text(json.dumps({"commit": rev, "dirty": False, "metrics": {**exact(reader(rev)), **tb}, "limits": limits}, indent=1) + "\n")
    out.write_text(json.dumps({"commit": commit, "dirty": dirty, "metrics": {**exact(reader(None)), **tr}, "limits": limits}, indent=1) + "\n")
    print(base_out, out)


if __name__ == "__main__":
    main()
