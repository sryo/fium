"""fium compare, noise and affects: what a change costs against a baseline, and which bench tasks it can move."""
import json, math, os, random, re, statistics, subprocess, sys
from fnmatch import fnmatch
from pathlib import Path

from check import git


# A run file: {"metrics": {name: {"dir": "lower"|"higher", "kind": time|tokens|count|bytes|quality|loc, "samples": [...]}},
#              "limits": {name: hard_max_or_min}}. Deterministic kinds (count, bytes, quality, loc) judge any move;
# noisy kinds (time, tokens) judge the bootstrap 95% range of the run/base median ratio against 1 ± rel.
# A limit kind is judged only against its limit. A move no bigger than the noise file's abs for that metric is same.

MIN_N = 5
NOISY = {"time", "tokens"}
DEFAULT_REL = 0.10


def lcg(seed):
    while True:
        seed = (seed * 1664525 + 1013904223) & 0xFFFFFFFF
        yield seed / 4294967296


def ratio_range(base, run, n=2000):
    # Paired reps (run alternately with the base) are judged on their rep-by-rep ratios: the bootstrap range of
    # the median ratio, in logs, with Lede's seeded generator, so the same run gets the same verdict anywhere.
    # A base rep of 0 counts as doubled when the run's isn't 0, unchanged when it is.
    if len(base) == len(run):
        ratios = [r / b if b > 0 else 2 if r > 0 else 1 for b, r in zip(base, run)]
        logs = [math.log(x) if x > 0 else -math.inf for x in ratios]
        rand = lcg(42)
        meds = sorted(statistics.median(logs[int(next(rand) * len(logs))] for _ in logs) for _ in range(n))
        return math.exp(meds[int(n * 0.025)]), math.exp(meds[math.ceil(n * 0.975) - 1])
    rng = random.Random(7)
    out = []
    for _ in range(n):
        b, r = [rng.choice(base) for _ in base], [rng.choice(run) for _ in run]
        mb = statistics.median(b)
        out.append(statistics.median(r) / mb if mb else float("inf"))
    out.sort()
    return out[int(0.025 * n)], out[int(0.975 * n) - 1]


def judge(name, base, run, rel, limit, abs_=0, cap=("ask", 0, 0)):
    if run is None or not run.get("samples") or not base.get("samples"):
        return {"metric": name, "verdict": "missing"}
    lower = base.get("dir", "lower") == "lower"
    b, r = base["samples"], run["samples"]
    mb, mr = statistics.median(b), statistics.median(r)
    row = {"metric": name, "base": mb, "run": mr}
    if limit is not None and ((mr > limit) if lower else (mr < limit)):
        return {**row, "verdict": "limit", "limit": limit}
    noisy = base.get("noisy", base.get("kind", "time") in NOISY)
    if base.get("kind") == "limit":
        v = "same"
    elif abs(mr - mb) <= abs_:
        v = "same"
    elif noisy and min(len(b), len(r)) < MIN_N:
        # Too few reps for a range (agent evals): judge the median against the band, and say so.
        point = mr / mb if mb else float("inf")
        if not lower:
            point = 1 / point if point else float("inf")
        v = "worse" if point > 1 + rel else "better" if point < 1 - rel else "same"
        row["low_n"] = True
    elif noisy:
        lo, hi = ratio_range(b, r)
        row["range"] = [round(lo, 4), round(hi, 4)]
        if not lower:
            lo, hi = 1 / hi if hi else float("inf"), 1 / lo if lo else float("inf")
        if lo > 1 + rel:
            v = "worse"
        elif hi < 1 - rel:
            v = "better"
        elif lo >= 1 - rel and hi <= 1 + rel:
            v = "same"
        else:
            v = "inconclusive"
    else:
        worse = mr > mb if lower else mr < mb
        better = mr < mb if lower else mr > mb
        v = "worse" if worse else "better" if better else "same"
    # The owner's cap (GOALS.md Caps:): free, no limit; ask, a move within the margin passes and past it the user
    # chooses; hard, it must end the same or better.
    level, pct, amount = cap
    row["cap"] = level
    if v == "worse" and (level == "free" or level == "ask" and abs(mr - mb) <= max(amount, pct * abs(mb))):
        v = "grew"
    return {**row, "verdict": v}


CAP_LINE = re.compile(r"^\s*(?:Caps|Topes):\s*`?([^`\n]+)`?", re.M | re.I)
CAP_ENTRY = re.compile(r"(\w+)(?:\+(\d+(?:\.\d+)?)(%?))?")
KINDS = ("quality", "tokens", "count", "loc", "bytes", "time")
# The digits Caps first used, like chmod's: a letter per kind and 3 hard, 2 ask, 1 ask+10%, 0 free; ":25" a percent.
OLD_KINDS = {"q": ["quality"], "k": ["tokens"], "n": ["count", "loc"], "b": ["bytes"], "t": ["time"]}
OLD_LEVEL = re.compile(r"([0-3])(?::(\d+(?:\.\d+)?))?")


def parse_caps(text):
    # "all=ask quality=hard bytes=ask+10% time=ask+200 t.js*=ask": a level per kind word, `all`, or metric glob,
    # read left to right; for each number the last entry that matches it wins. Only ask takes a margin, a percent
    # or an amount. Returns [(key, (level, pct, amount))]; a line in the old digits reads as what it meant.
    m = CAP_LINE.search(text or "")
    out = []
    for tok in (m.group(1).split() if m else []):
        key, eq, val = tok.rpartition("=")
        old = OLD_LEVEL.fullmatch(val) if eq else (tok[0] in OLD_KINDS and OLD_LEVEL.fullmatch(tok[1:]))
        if old:
            lvl, pct = old.groups()
            level = {"3": "hard", "0": "free"}.get(lvl, "ask")
            pct = float(pct) / 100 if pct else 0.10 if lvl == "1" else 0
            out += [(k, (level, pct if level == "ask" else 0, 0)) for k in ([key] if eq else OLD_KINDS[tok[0]])]
            continue
        e = CAP_ENTRY.fullmatch(val) if eq else None
        if not e or e.group(1) not in ("hard", "ask", "free"):
            sys.exit(f"Caps: {tok!r} isn't kind=level; the level is hard, ask or free, like `all=ask bytes=ask+10% t.js*=hard`")
        level, n, pct = e.groups()
        if n and level != "ask":
            sys.exit(f"Caps: {tok!r}: only ask takes a margin (ask+10% or ask+200)")
        out.append((key, (level, float(n) / 100 if n and pct else 0, float(n) if n and not pct else 0)))
    return out


def caps_line(caps):
    # The line in words, to write in place of an old digit one.
    word = lambda c: c[0] + (f"+{c[1] * 100:g}%" if c[1] else f"+{c[2]:g}" if c[2] else "")
    return "Caps: `" + " ".join(f"{k}={word(c)}" for k, c in caps) + "`"


def old_caps(text):
    m = CAP_LINE.search(text or "")
    return bool(m and any(OLD_LEVEL.fullmatch(t.rpartition("=")[2] if "=" in t else t[1:]) for t in m.group(1).split()))


def cap_overrides(caps):
    return [k for k, _ in caps if k != "all" and k not in KINDS]


def cap_for(name, kind, caps):
    for key, cap in reversed(caps):
        if key == "all" or key == kind or key not in KINDS and fnmatch(name, key):
            return cap
    return ("ask", 0, 0)


def goals_text(path):
    p = Path(path).resolve()
    top = git(p if p.is_dir() else p.parent, "rev-parse", "--show-toplevel").stdout.strip()
    p = Path(top) / "GOALS.md" if top else None
    return p.read_text() if p and p.exists() else ""


def noise_file(path):
    # The project's A/A noise (fium noise): bench/noise.json, else an eval's own tests/eval/noise.json.
    # Found by walking up to the checkout's top, not by asking git: compare runs on every attempt.
    p = Path(path).resolve()
    p = p if p.is_dir() else p.parent
    top = next((d for d in (p, *p.parents) if (d / ".git").exists()), p)
    return next((str(f) for f in (top / "bench" / "noise.json", top / "tests" / "eval" / "noise.json") if f.exists()), None)


def price_compare(base_path, run_path, noise_path=None, repo=None):
    base, run = json.load(open(base_path)), json.load(open(run_path))
    noise_path = noise_path or noise_file(repo or run_path)
    noise = json.load(open(noise_path)) if noise_path else {}
    rel, abs_ = noise.get("rel", {}), noise.get("abs", {})
    limits = {**base.get("limits", {}), **run.get("limits", {})}
    caps = parse_caps(goals_text(repo or base_path))
    return [judge(n, m, run["metrics"].get(n), rel.get(n, DEFAULT_REL), limits.get(n), abs_.get(n, 0),
                  cap_for(n, m.get("kind", "time"), caps))
            for n, m in base["metrics"].items()]


def noise(base_path, run_path, floor=DEFAULT_REL, abs_globs=()):
    # rel: how far the A/A's range (as compare prints it) strays from 1, rounded up to a whole percent, at least floor.
    base, run = json.load(open(base_path))["metrics"], json.load(open(run_path))["metrics"]
    rel, abs_ = {}, {}
    for n, m in base.items():
        b, r = m.get("samples") or [], (run.get(n) or {}).get("samples") or []
        # Like compare, a metric with fewer than MIN_N reps on a side has no range to take noise from.
        if min(len(b), len(r)) < MIN_N or not m.get("noisy", m.get("kind", "time") in NOISY):
            continue
        lo, hi = (round(x, 4) for x in ratio_range(b, r))
        rel[n] = max(floor, math.ceil(max(1 - lo, hi - 1) * 100 - 1e-9) / 100)
        for g, v in abs_globs:
            if fnmatch(n, g):
                abs_[n] = v
    return {"rel": rel, "abs": abs_}


INERT = ["README.md", "GOALS.md", "AGENTS.md", "CLAUDE.md", "LICENSE", "test/*", "tests/*", "*noise.json", "*baseline.json"]


def changed_since(repo, rev):
    # None when rev isn't an ancestor of HEAD: then nothing can be carried over.
    if git(repo, "merge-base", "--is-ancestor", rev, "HEAD").returncode:
        return None
    return git(repo, "diff", "--name-only", rev, "HEAD").stdout.split()


def globs(repo, name, defaults):
    # bench/<name>: a glob per line, # comments; a !defaults line drops the defaults. The file itself always matches.
    p = Path(repo) / "bench" / name
    lines = [l.strip() for l in p.read_text().splitlines() if l.strip() and not l.startswith("#")] if p.exists() else []
    return [f"bench/{name}"] + [l for l in lines if l != "!defaults"] + ([] if "!defaults" in lines else defaults)


def inert_globs(repo):
    # Agent-facing docs (SKILL.md, references/) change what a run measures, so they are never inert by default.
    return globs(repo, "inert", INERT)


def stale_row(run_path, repo):
    # A run says which commit it measured, so an old or dirty run can't pass for this change (K1, K2).
    run = json.load(open(run_path))
    sha = run.get("commit")
    if not sha:
        return {"metric": "(commit)", "verdict": "unstamped"}
    head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    row = {"metric": "(commit)", "base": head[:12] or None, "run": sha[:12] + ("+dirty" if run.get("dirty") else "")}
    if len(sha) < 7 or run.get("dirty"):
        return {**row, "verdict": "stale"}
    if head.startswith(sha):
        return None
    files, globs = changed_since(repo, sha), inert_globs(repo)
    if files is not None and all(any(fnmatch(f, g) for g in globs) for f in files):
        return {**row, "verdict": "carried"}
    return {**row, "verdict": "stale"}


def env_row(base, run):
    # A run an agent made says which model and Claude Code made it: another model's numbers aren't this change's, and
    # another CLI version is shown, since it updates itself often.
    b, r = base.get("env") or {}, run.get("env") or {}
    if not (b or r):
        return None
    say = lambda e: " ".join(str(e[k]) for k in ("model", "claude_code_version") if e.get(k)) or None
    row = {"metric": "(env)", "base": say(b), "run": say(r)}
    if not (b and r):
        return {**row, "verdict": "unstamped"}
    if b.get("model") != r.get("model"):
        return {**row, "verdict": "not comparable"}
    if b.get("claude_code_version") != r.get("claude_code_version"):
        return {**row, "verdict": "changed"}
    return None


# Runs live outside the repo, in ~/.fium/runs/<repo>/, so no checkout tracks, cleans or loses them. Every clean,
# stamped run a compare judges is kept there by commit, so a later compare names its base by rev from any cwd.
RUNS = Path(os.environ.get("FIUM_HOME") or "~/.fium").expanduser() / "runs"


def runs_dir(repo):
    # Named after the main checkout, so a worktree's runs land with its repo's.
    common = git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir").stdout.strip()
    return RUNS / (Path(common).parent.name if common else Path(repo).resolve().name)


def keep_runs(repo, *paths):
    for p in paths:
        run = json.load(open(p))
        if len(run.get("commit") or "") == 40 and not run.get("dirty"):
            runs_dir(repo).mkdir(parents=True, exist_ok=True)
            (runs_dir(repo) / f"{run['commit']}.json").write_text(json.dumps(run))


def find_run(rev, repo):
    if Path(rev).is_file():
        return rev
    sha = git(repo, "rev-parse", "--verify", "-q", f"{rev}^{{commit}}").stdout.strip() or rev
    hits = sorted(runs_dir(repo).glob(f"{sha}*.json")) if re.fullmatch(r"[0-9a-f]{4,40}", sha) else []
    if not hits:
        sys.exit(f"fium: {rev} is neither a run file nor a commit with a run in {runs_dir(repo)}; run the bench on it, or pass the file")
    return str(hits[0])


def affects(repo, revs, rules_file):
    # Which bench tasks a change can move. A file no rule matches could move anything, so it means all.
    rules = json.load(open(rules_file))["rules"]
    base = revs.split("..")[0]
    files = changed_since(repo, base)
    if files is None:
        return {"tasks": "*", "why": {base: "not an ancestor of HEAD"}}
    tasks, why = set(), {}
    for f in files:
        hit = next((r["tasks"] for r in rules if any(fnmatch(f, g) for g in r["files"])), None)
        if hit is None and any(fnmatch(f, g) for g in inert_globs(repo)):
            hit = "none"
        why[f] = hit if hit is not None else "*"
        if why[f] == "*":
            tasks = "*"
        elif why[f] != "none" and tasks != "*":
            tasks |= set(why[f])
    return {"tasks": tasks if tasks == "*" else sorted(tasks), "why": why}


def affects_main(a):
    res = affects(a.repo, a.revs, a.rules or str(Path(a.repo) / "bench" / "affects.json"))
    if a.json:
        print(json.dumps(res, indent=2))
    else:
        print("all tasks" if res["tasks"] == "*" else " ".join(res["tasks"]) or "no tasks: nothing a bench measures changed")



def change(base, run):
    if not all(isinstance(v, (int, float)) for v in (base, run)):
        return f"{base} -> {run}"
    d = run - base
    if not d:
        return f"{run:g}"
    pct = f", {d / base * 100:+.3g}%" if base else ""
    return f"{base:g} -> {run:g} ({d:+g}{pct})"


def compare_main(a):
    base = find_run(a.base, a.repo or ".")
    rows = price_compare(base, a.run, a.noise, (a.repo or ".") if base != a.base else None)
    keep_runs(a.repo or ".", base, a.run)
    stale = stale_row(a.run, a.repo or ".")
    env = env_row(json.load(open(base)), json.load(open(a.run)))
    rows += [x for x in (stale, env) if x]
    if a.json:
        print(json.dumps(rows))
    else:
        for r in rows:
            print(f"{r['verdict'] + ('?' if r.get('low_n') else ''):>12}  {r['metric']}: {change(r.get('base'), r.get('run'))}" + (f"  range {r['range']}" if "range" in r else ""))
    vs = {r["verdict"] for r in rows}
    if stale and not a.json:
        fix = ("stamp the run with \"commit\": git rev-parse HEAD and \"dirty\": whether git status --porcelain is non-empty"
               if stale["verdict"] == "unstamped" else
               "only inert files (bench/inert) changed since the run, so its numbers stand" if stale["verdict"] == "carried" else
               "commit, then rerun the bench on HEAD (or list the changed files in bench/inert if no bench reads them)")
        print(f"  {stale['verdict']}: {fix}", file=sys.stderr)
    if env and env["verdict"] == "not comparable" and not a.json:
        print("  not comparable: measure the base again on the run's model", file=sys.stderr)
    sys.exit(1 if vs & {"worse", "limit", "missing", "stale", "not comparable"} else 3 if "inconclusive" in vs else 0)

