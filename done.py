"""fium done: can this change merge? Every How we know row, measured where it left the base branch and now."""
import json, re, shutil, statistics, subprocess, sys, tempfile, time
from fnmatch import fnmatch
from pathlib import Path

from check import git
from compare import DEFAULT_REL, cap_for, cap_overrides, caps_line, change, env_row, judge, noise_file, old_caps, parse_caps, runs_dir


def how_we_know(goals):
    # Each row's Run cell: `cmd` runs here and at the base; costly: `cmd` too, but only with --costly (an agent eval
    # spends tokens); live: `cmd` reads live state, so it runs only here. Anything else is for the user to check by
    # hand. A table without a Run column still lists its rows, so none goes missing.
    m = re.search(r"^## How we know\n(.*?)(?=^## |\Z)", goals, re.M | re.S)
    lines = [l for l in (m.group(1).splitlines() if m else []) if l.startswith("|")]
    if not lines:
        return []
    # A cell may hold a pipe written \|, as in a shell command.
    split = lambda l: [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", l.strip().strip("|"))]
    head = [c.lower() for c in split(lines[0])]
    rows = []
    for l in lines[2:]:
        cells = split(l)
        run = cells[head.index("run")] if "run" in head and len(cells) > head.index("run") else ""
        m = re.fullmatch(r"(?:(live|costly):\s*)?`(.+)`", run)
        rows.append({"goal": cells[0], "metric": cells[1] if len(cells) > 1 else "", "cmd": m[2] if m else None,
                     "kind": m[1] if m else None, "by_hand": run, "text": l,
                     "where": cells[head.index("where")] if "where" in head and len(cells) > head.index("where") else ""})
    return rows


def execute(cmd, cwd):
    # What a command printed, kept raw so a cached base is read the same way as a fresh one.
    t = time.monotonic()
    r = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    raw = {"code": r.returncode, "s": round(time.monotonic() - t, 2), "out": r.stdout[-20000:], "err": r.stderr[-20000:]}
    lines = r.stdout.strip().splitlines()
    last = lines[-1].strip() if lines else ""
    if last.endswith(".json") and (Path(cwd) / last).is_file():
        raw["run"] = json.loads((Path(cwd) / last).read_text())
    return raw


def measure(raw, name):
    # A command's last line is either a run file (RULES.md K1), whose metrics count, or a number, named after its row.
    out = {"ok": raw["code"] == 0, "s": raw["s"], "metrics": {}, "limits": {}}
    lines = raw["out"].strip().splitlines()
    last = lines[-1].strip() if lines else ""
    if "run" in raw:
        out["metrics"], out["limits"] = dict(raw["run"].get("metrics", {})), raw["run"].get("limits", {})
        out["env"] = raw["run"].get("env")
    elif re.match(r"-?\d+(\.\d+)?(\s|$)", last) and not re.match(r"\d+ passed", last):
        # Its kind, for the row's cap, comes from the row's words: bytes, time, tokens, else a count.
        kind = next((k for k, w in (("bytes", r"bytes|\bKB\b|\bMB\b"), ("time", r"\bms\b|seconds|\btime\b"), ("tokens", r"tokens"))
                     if re.search(w, name, re.I)), "count")
        out["metrics"] = {name: {"dir": "lower", "kind": kind, "samples": [float(last.split()[0])]}}
    else:
        out["last"] = last[:80]
    # A test runner's count of passing tests (node --test, unittest, pytest): fewer tests means less checked.
    tests = re.findall(r"^[ℹ#] pass (\d+)$|^Ran (\d+) tests?|(\d+) passed", raw["out"] + raw["err"], re.M)
    if tests:
        # A command may run several runners; their counts add up.
        out["metrics"]["tests passing"] = {"dir": "higher", "kind": "count",
                                           "samples": [float(sum(int(next(x for x in t if x)) for t in tests))]}
    return out


def at_base(repo, sha, cmds, fresh=()):
    # The base is measured once per commit, in a throwaway worktree beside the repo (so a test that looks for a sibling
    # checkout finds it), and kept only so the next done needn't redo it.
    cache = runs_dir(repo) / f"done-{sha}.raw.json"
    have = json.loads(cache.read_text()) if cache.exists() else {}
    # A costly row runs against the live world (a browser's tabs, a model), so its base is measured now, beside the
    # current tree, never read back from an earlier run.
    # A confirmed keep's runs (fium try --confirm) are its measurement, costly ones included.
    need = [c for c in cmds if c not in have or c in fresh and not have[c].get("confirmed")]
    if need:
        tmp = Path(tempfile.mkdtemp(prefix=f".fium-done-{repo.name}-", dir=repo.parent))
        wt = tmp
        tmp.rmdir()
        git(repo, "worktree", "add", "--detach", "-q", str(wt), sha)
        try:
            for dep in ("node_modules", ".venv"):
                if (repo / dep).is_dir():
                    (wt / dep).symlink_to(repo / dep)
            for c in need:
                have[c] = execute(c, wt)
        finally:
            git(repo, "worktree", "remove", "--force", str(wt))
            shutil.rmtree(tmp, ignore_errors=True)
        cache.parent.mkdir(parents=True, exist_ok=True)
        # A failed measurement isn't kept, so the next done tries it again.
        cache.write_text(json.dumps({c: x for c, x in have.items() if x["code"] == 0 and (c not in fresh or x.get("confirmed"))}))
    return have


def live_before(repo, sha):
    # Live state has no commit to read it at, so a change's before for its live rows is read once, when the plan is
    # frozen (K3), and kept beside the base's cache.
    f = runs_dir(repo) / f"done-{sha}.live.json"
    return f, (json.loads(f.read_text()) if f.exists() else {})


def start(repo, sha, print=print):
    goals = (repo / "GOALS.md").read_text() if (repo / "GOALS.md").exists() else ""
    rows = [r for r in how_we_know(goals) if r["kind"] == "live"]
    f, have = live_before(repo, sha)
    if have:
        print(f"fium done --start: this change's before was read at {have['at']}; delete {f} to read it again")
        return 1
    raw = {r["cmd"]: execute(r["cmd"], repo) for r in rows}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "raw": raw}))
    print(f"fium done --start: before of {len(rows)} live rows, against {sha[:7]}")
    for r in rows:
        print(f"  {r['metric']}: " + reading(measure(raw[r["cmd"]], r["metric"]), r))
    return 0


def named(name, text):
    return bool(re.search(r"(?<![\w.])" + re.escape(name) + r"(?!\w)", text, re.I))


def claims(name, text):
    # A row names a metric by its exact name, or by a pattern in backticks where <...> stands for any part.
    return bool(named(name, text) or any(
        re.fullmatch(re.sub(r"<[^>]+>", ".+", re.escape(p).replace("\\<", "<").replace("\\>", ">")), name)
        for p in re.findall(r"`([^`]*<[^`>]+>[^`]*)`", text)))


def reading(m, row):
    # What a row read: its one number, or a run file's metrics, those the row names first.
    ms = m["metrics"]
    if not ms:
        return m.get("last") or "no output"
    mine = [n for n in ms if claims(n, row["where"]) or claims(n, row["text"])] or list(ms)
    return ", ".join((f"{n}: " if len(ms) > 1 or n != row["metric"] else "") + f"{statistics.median(ms[n]['samples']):g}" for n in mine)


def short(cmd):
    return cmd if len(cmd) <= 60 else cmd[:57] + "..."


def base_branch(repo, base=None):
    return base or next((b for b in ("main", "master") if not git(repo, "rev-parse", "-q", "--verify", b).returncode), "HEAD")


def done_main(a):
    repo = Path(git(".", "rev-parse", "--show-toplevel").stdout.strip() or ".").resolve()
    branch = base_branch(repo, a.base)
    if a.start:
        sys.exit(start(repo, git(repo, "merge-base", branch, "HEAD").stdout.strip()))
    res = done(repo, git(repo, "merge-base", branch, "HEAD").stdout.strip(), branch, a.costly)
    if res["blocked"] or res["hard"] or res["other_model"]:
        sys.exit(1)
    if res["grew"] or res["pending"] or res["unmeasured"]:
        sys.exit(3)
    print("Nothing got worse past its cap and nothing broke: it can merge.")


def done(repo, sha, branch, costly=False, print=print):
    # Every How we know row at sha and now, printed under its goal; returns what blocks, what grew and each verdict.
    goals = (repo / "GOALS.md").read_text() if (repo / "GOALS.md").exists() else ""
    rows = how_we_know(goals)
    dirty = bool(git(repo, "status", "--porcelain").stdout.strip())
    label = {}
    for r in rows:
        label.setdefault(r["cmd"], r["metric"])
    # A live row whose before was read (start) is held to it like any row.
    read = {c: x for c, x in live_before(repo, sha)[1].get("raw", {}).items() if c in label and measure(x, label[c])["metrics"]}
    for r in rows:
        if r["kind"] == "live" and r["cmd"] in read:
            r["kind"] = None
    cmds = list(dict.fromkeys(r["cmd"] for r in rows if r["cmd"] and (not r["kind"] or r["kind"] == "costly" and costly)))
    costly = {r["cmd"] for r in rows if r["kind"] == "costly"}
    have = {**at_base(repo, sha, [c for c in cmds if c not in read], costly), **read}
    base = {c: measure(raw, label[c]) for c, raw in have.items() if c in cmds}
    raw = {c: execute(c, repo) for c in cmds + [r["cmd"] for r in rows if r["kind"] == "live"]}
    here = {c: measure(x, label[c]) for c, x in raw.items()}
    caps = parse_caps(goals)
    nf = noise_file(repo)
    noise = json.loads(Path(nf).read_text()) if nf else {}
    rel = lambda name: noise.get("rel", {}).get(name, DEFAULT_REL)
    print(f"fium done: {'this tree' if dirty else 'HEAD'} against {branch} at {sha[:7]}")
    # Each row shows under its goal's name from the Goals list, so nobody has to look a number up.
    titles = dict(re.findall(r"^(\d+)\.\s+\*\*(.+?)\.?\*\*", goals.split("## How we know")[0], re.M))
    shown = None
    # A command's metrics show under the row whose Where names them, else whose text does, else its first row.
    owner = {}
    names = claims
    for c in cmds:
        users = [i for i, r in enumerate(rows) if r["cmd"] == c and r["kind"] != "live"]
        for name in {**base[c]["metrics"], **here[c]["metrics"]}:
            owner[(c, name)] = ([i for i in users if names(name, rows[i]["where"])] or
                                [i for i in users if names(name, rows[i]["text"])] or users)[0]
    blocked, hard, grew, pending, unmeasured, other_model, failed, verdicts = [], [], [], [], [], [], [], {}
    for r in rows:
        if r["goal"] != shown:
            print(titles.get(r["goal"], f"Goal {r['goal']}"))
            shown = r["goal"]
        print(f"  {r['metric']}")
        c = r["cmd"]
        if not c:
            print(f"       {r['by_hand'] or 'no Run cell'}: check it yourself")
            continue
        if r["kind"] == "live":
            got = here[c]["metrics"]
            print(f"       live `{short(c)}`: " + (reading(here[c], r) + " now" if got else ("" if here[c]["ok"] else "fails, ")
                                                     + (here[c].get("last") or "no output")))
            # Live state is the row's only reading, so a row that read no number measured nothing.
            unmeasured.append(f"{r['metric']} (live: {'no before' if got else 'printed no number' if here[c]['ok'] else 'fails'})")
            continue
        if c not in here:
            print(f"       costly `{short(c)}`: not run; state its cost, then fium done --costly")
            pending.append(r["metric"])
            continue
        b, h = base[c], here[c]
        i = rows.index(r)
        state = ("ok" if b["ok"] else "ok now, failed at the base") if h["ok"] else "fails" + ("" if b["ok"] else " (failed at the base too)")
        if i == min(j for j, x in enumerate(rows) if x["cmd"] == c and x["kind"] != "live"):
            print(f"       `{short(c)}`: {state}, {b['s']:g}s -> {h['s']:g}s")
            env = env_row(b, h)
            if env:
                print(f"     {env['verdict']:>9}  model: {change(env['base'], env['run'])}")
            if env and env["verdict"] == "not comparable":
                other_model.append(short(c))
            if b["ok"] and not h["ok"]:
                blocked.append(c)
                failed.append(short(c))
            elif not b["ok"]:
                # A command that failed at the base measured nothing to hold now against, for every row that runs it.
                why = "fails before and after" if not h["ok"] else "failed at the base"
                unmeasured += [f"{x['metric']} ({why})" for x in rows if x["cmd"] == c and x["kind"] != "live"]
        else:
            print(f"       `{short(c)}`: {state}, as above")
        mine = [n for n in {**b["metrics"], **h["metrics"]} if owner[(c, n)] == i]
        for name in mine:
            if name not in b["metrics"]:
                print(f"     {'new':>9}  {name}: {statistics.median(h['metrics'][name]['samples']):g}")
        same = 0
        for name, m in b["metrics"].items():
            if name not in mine:
                continue
            v = judge(name, m, h["metrics"].get(name), rel(name), {**b["limits"], **h["limits"]}.get(name), noise.get("abs", {}).get(name, 0),
                      cap_for(name, m.get("kind", "time"), caps))
            verdicts[name] = {**v, "kind": m.get("kind", "time"), "dir": m.get("dir", "lower")}
            # An unchanged number still shows when its row or a Caps override names it: those are the ones watched.
            if v["verdict"] == "same" and len(mine) > 3 and not (
                    named(name, r["text"]) or any(fnmatch(name, g) for g in cap_overrides(caps))):
                same += 1
                continue
            shown = "dropped" if v["verdict"] == "grew" and m.get("dir") == "higher" else v["verdict"]
            print(f"     {shown + ('?' if v.get('low_n') else ''):>9}  {name}: {change(v.get('base'), v.get('run'))}")
            if v["verdict"] in ("limit", "missing"):
                blocked.append(name)
            elif v["verdict"] == "worse" or v["verdict"] == "inconclusive" and v["base"] and (
                    v["run"] / v["base"] > 1 + rel(name) if m.get("dir", "lower") == "lower" else v["run"] / v["base"] < 1 - rel(name)):
                # Inconclusive counts only when its median moved past the noise band the wrong way.
                (hard if v["cap"] == "hard" else grew).append(name)
        if same:
            print(f"     {same} same")
    # Caps (GOALS.md): a hard number that got worse isn't done until it's the same or better, or the user agrees it
    # can't get there without lowering quality; an ask one past its margin merges only if the user lets it.
    blocked, hard, grew = (list(dict.fromkeys(x)) for x in (blocked, hard, grew))
    if blocked:
        print(f"Not done: {', '.join(blocked)} broke or crossed a limit. Fix it.")
    if other_model:
        print(f"Not done: {', '.join(other_model)} ran on another model at the base. Measure both on the same model.")
    if hard:
        print(f"Not done: {', '.join(hard)} (hard) got worse. Make it the same or better, or agree with the user it can't be without lowering quality.")
    if grew:
        print(f"{', '.join(grew)} got worse past its margin. Simplify it, or the user lets it pass.")
    if old_caps(goals):
        print(f"GOALS.md's Caps line uses the old digits. Write it in words: {caps_line(caps)}")
    if pending and not (blocked or hard):
        print(f"Not measured yet: {', '.join(dict.fromkeys(pending))} (costly). It isn't done until they run, or the user says they needn't.")
    if unmeasured:
        print(f"Couldn't measure: {', '.join(unmeasured)}. It isn't done until they run clean, or the user says they needn't.")
        if any(u.endswith("(live: no before)") for u in unmeasured):
            print("A live row's before is read once, when the plan is frozen: fium done --start.")
    return {"blocked": blocked, "hard": hard, "grew": grew, "pending": pending, "unmeasured": unmeasured,
            "other_model": other_model, "failed": failed, "verdicts": verdicts, "raw": {c: raw[c] for c in costly & set(cmds)}}
