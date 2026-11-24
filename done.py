"""fium done: can this change merge? Every How we know row, measured where it left the base branch and now."""
import hashlib, json, os, re, shutil, signal, statistics, subprocess, sys, tempfile, time
from fnmatch import fnmatch
from pathlib import Path

from check import CODE_EXT, SKIP_DIRS, base_branch, columns, git, metrics_table
from compare import DEFAULT_REL, NOISY, cap_for, cap_overrides, caps_line, change, env_row, globs, judge, noise_file, old_caps, parse_caps, runs_dir


def how_we_know(goals):
    # Each row's Run cell: `cmd` runs here and at the base; costly: `cmd` too, but only with --costly (an agent eval
    # spends tokens); live: `cmd` reads live state, so it runs only here. Anything else is for the user to check by
    # hand. A table without a Run column still lists its rows, so none goes missing.
    lines = metrics_table(goals)[1]
    if not lines:
        return []
    # A cell may hold a pipe written \|, as in a shell command.
    split = lambda l: [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", l.strip().strip("|"))]
    where_at, run_at = columns([c.lower() for c in split(lines[0])])
    cell = lambda cells, i: cells[i] if i is not None and len(cells) > i else ""
    rows = []
    for l in lines[2:]:
        cells = split(l)
        run = cell(cells, run_at)
        m = re.fullmatch(r"(?:(live|costly):\s*)?`(.+)`", run)
        rows.append({"goal": cells[0], "metric": cells[1] if len(cells) > 1 else "", "cmd": m[2] if m else None,
                     "kind": m[1] if m else None, "by_hand": run, "text": l,
                     "where": cell(cells, where_at)})
    return rows


# What judges a change, unless bench/judge names it: the benches, their baselines and noise bands. A test file is the
# change's own to write (W2), so done leaves tests out; fium try's loop holds them too.
JUDGE = ["bench/*", "test/*", "tests/*", "*noise.json", "*baseline.json"]


# Seconds a row's command may run before it and everything it started are stopped (fium done --timeout).
TIMEOUT = 3600


def execute(cmd, cwd):
    # What a command printed, kept raw so a cached base is read the same way as a fresh one.
    t = time.monotonic()
    p = subprocess.Popen(cmd, shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        (out, err), hung = p.communicate(timeout=TIMEOUT), None
    except BaseException as e:
        # Its own session holds whatever it started, so a server or an eval it left behind goes too, also when done
        # itself is stopped (a timeout's SIGTERM, ^C).
        os.killpg(p.pid, signal.SIGKILL)
        if not isinstance(e, subprocess.TimeoutExpired):
            raise
        (out, err), hung = p.communicate(), TIMEOUT
    raw = {"code": 124 if hung else p.returncode, "s": round(time.monotonic() - t, 2), "out": out[-20000:], "err": err[-20000:], "timeout": hung}
    lines = out.strip().splitlines()
    last = lines[-1].strip() if lines else ""
    if last.endswith(".json") and (Path(cwd) / last).is_file():
        raw["run"] = json.loads((Path(cwd) / last).read_text())
    return raw


def measure(raw, name):
    # A command's last line is either a run file (RULES.md K1), whose metrics count, or a number, named after its row.
    out = {"ok": raw["code"] == 0, "s": raw["s"], "metrics": {}, "limits": {}, "fails": f"timed out after {raw['timeout']}s" if raw.get("timeout") else "fails"}
    lines = raw["out"].strip().splitlines()
    last = lines[-1].strip() if lines else ""
    if "run" in raw:
        out["metrics"], out["limits"] = dict(raw["run"].get("metrics", {})), raw["run"].get("limits", {})
        out["env"] = raw["run"].get("env")
        # A metric with a sample that isn't a number (a bench that wrote null) measured nothing; it's named, not judged.
        num = lambda x: isinstance(x, (int, float)) and not isinstance(x, bool)
        out["no_number"] = [n for n, m in out["metrics"].items() if not (m.get("samples") and all(map(num, m["samples"])))]
        for n in out["no_number"]:
            del out["metrics"][n]
    elif re.match(r"-?\d+(\.\d+)?(\s|$)", last) and not re.match(r"\d+ passed", last):
        # Its kind, for the row's cap, comes from the row's words: bytes, time, tokens, else a count.
        kind = next((k for k, w in (("bytes", r"bytes|\bKB\b|\bMB\b"), ("time", r"\bms\b|seconds|\btime\b"), ("tokens", r"tokens"))
                     if re.search(w, name, re.I)), "count")
        out["metrics"] = {name: {"dir": "lower", "kind": kind, "samples": [float(last.split()[0])]}}
    else:
        out["last"] = last[:80]
    # A test runner's count of passing tests (node --test, unittest, pytest): fewer tests means less checked.
    text = raw["out"] + raw["err"]
    tests = re.findall(r"^[ℹ#] pass (\d+)$|^Ran (\d+) tests?|(\d+) passed", text, re.M)
    if tests:
        # A command may run several runners; their counts add up. unittest's "Ran N" counts every test it ran or
        # skipped, so its summary's skips, failures and errors come off: a skipped test checks nothing.
        not_passing = re.findall(r"(?:skipped|failures|errors)=(\d+)", " ".join(re.findall(r"^(?:OK|FAILED) \((.*)\)$", text, re.M)))
        passing = sum(int(next(x for x in t if x)) for t in tests) - sum(map(int, not_passing))
        out["metrics"]["tests passing"] = {"dir": "higher", "kind": "count", "samples": [float(passing)]}
    return out


def at_base(repo, sha, cmds, fresh=(), timed=lambda c, x: False, now=None):
    # The base is measured once per commit, in a throwaway worktree beside the repo (so a test that looks for a sibling
    # checkout finds it), and kept only so the next done needn't redo it.
    cache = runs_dir(repo) / f"done-{sha}.raw.json"
    have = json.loads(cache.read_text()) if cache.exists() else {}
    # A costly row runs against the live world (a browser's tabs, a model), so its base is measured now, beside the
    # current tree, never read back from an earlier run.
    # A confirmed keep's runs (fium try --confirm) are its measurement, costly ones included.
    # A timing kept from an earlier run measured the machine as it was then; it's timed again, and now right after it
    # (into now), so the load both see is the same.
    need = [c for c in cmds if c not in have or not have[c].get("confirmed") and (c in fresh or now is not None and timed(c, have[c]))]
    if need:
        clear_left(repo)
        # A timeout stops done or try with SIGTERM; exiting instead of dying lets it remove its copy on the way out.
        for sig in (signal.SIGTERM, signal.SIGHUP):
            signal.signal(sig, lambda n, _: sys.exit(128 + n))
        wt = Path(tempfile.mkdtemp(prefix=f".fium-done-{repo.name}-{os.getpid()}-", dir=repo.parent))
        wt.rmdir()
        git(repo, "worktree", "add", "--detach", "-q", str(wt), sha)
        try:
            for dep in ("node_modules", ".venv"):
                if (repo / dep).is_dir():
                    (wt / dep).symlink_to(repo / dep)
            for c in need:
                have[c] = execute(c, wt)
                if now is not None and timed(c, have[c]):
                    now[c] = execute(c, repo)
        finally:
            git(repo, "worktree", "remove", "--force", str(wt))
            shutil.rmtree(wt, ignore_errors=True)
        cache.parent.mkdir(parents=True, exist_ok=True)
        # A failed measurement isn't kept, so the next done tries it again.
        cache.write_text(json.dumps({c: x for c, x in have.items() if x["code"] == 0 and (c not in fresh or x.get("confirmed"))}))
    return have


def clear_left(repo):
    # A done killed outright (SIGKILL) leaves its copy of the base; its name holds its pid, so one still running stays.
    prefix = str(repo.parent.resolve() / f".fium-done-{repo.name}-")
    for wt in re.findall(r"^worktree (.+)$", git(repo, "worktree", "list", "--porcelain").stdout, re.M):
        pid = wt[len(prefix):].split("-")[0] if wt.startswith(prefix) else ""
        try:
            pid.isdigit() and os.kill(int(pid), 0)
        except ProcessLookupError:
            git(repo, "worktree", "remove", "--force", wt)
        except PermissionError:
            pass


def live_before(repo, sha):
    # Live state has no commit to read it at, so a change's before for its live rows is read once, when the plan is
    # frozen (K3), and kept beside the base's cache.
    f = runs_dir(repo) / f"done-{sha}.live.json"
    return f, (json.loads(f.read_text()) if f.exists() else {})


def contract_file(repo, sha):
    # What this change set out to do, agreed when the plan was frozen (W1), kept beside the base's cache, never in the repo (K3).
    return runs_dir(repo) / f"done-{sha}.contract.json"


def agree(repo, sha, expect, print=print):
    f = contract_file(repo, sha)
    if f.exists():
        have = json.loads(f.read_text())
        print(f"fium done --start: this change's contract was agreed at {have['at']}: {'; '.join(i['what'] for i in have['items'])}. "
              f"Changing it is the user's call: on their word, delete {f} and --start again")
        return 1
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"at": time.strftime("%Y-%m-%dT%H:%M:%S"), "items": [{"what": w, "cmd": c} for w, c in expect]}))
    save_verdict(repo, None, [], unmet=[w for w, _ in expect], base=sha)
    print(f"fium done --start: the contract, against {sha[:7]}: {'; '.join(w for w, _ in expect)}")
    return 0


def start(repo, sha, expect=(), print=print):
    if expect and agree(repo, sha, expect, print):
        return 1
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


# Fewer net lines than this is a fix or a tweak; at this many a change adds something a user can do.
ADDS = 20


def code(f):
    # Tests, benches and docs aren't code here.
    return Path(f).suffix in CODE_EXT and not Path(f).name.startswith(".") and not (SKIP_DIRS | {"bench"}) & set(Path(f).parts)


def added_code(repo, sha):
    # Net lines of code the change adds since sha, files not yet added included.
    n = 0
    for l in git(repo, "diff", "--numstat", sha).stdout.splitlines():
        a, d, f = l.split("\t", 2)
        if a != "-" and code(f):
            n += int(a) - int(d)
    for f in git(repo, "ls-files", "--others", "--exclude-standard").stdout.splitlines():
        if code(f):
            n += len((repo / f).read_text(errors="ignore").splitlines()) if (repo / f).is_file() else 0
    return n


def changed(repo, sha):
    # The change since sha as one hash, the same before a commit and after it; None when nothing changed. Code not yet
    # added counts; other untracked files don't, since a bench leaves its run files there.
    new = [f for f in git(repo, "ls-files", "--others", "--exclude-standard").stdout.splitlines() if code(f) and (repo / f).is_file()]
    diff = git(repo, "diff", sha).stdout + "".join(f + (repo / f).read_text(errors="ignore") for f in new)
    return hashlib.sha256(diff.encode()).hexdigest()[:16] if diff else None


def paths(where):
    # The files a by-hand row covers: its Where cell's backticked paths or globs. A command (it has a space) isn't one.
    return [w for w in re.findall(r"`([^`]+)`", where) if " " not in w]


def touched(repo, sha, globs):
    # Whether the change since sha, files not yet added included, touches any of globs.
    files = git(repo, "diff", "--name-only", sha).stdout.splitlines() + git(repo, "ls-files", "--others", "--exclude-standard").stdout.splitlines()
    return any(fnmatch(f, g) for f in files for g in globs)


def looked(repo, sha):
    # What was looked at for each by-hand row of this change (W6), kept beside the base's cache, never in the repo (K3).
    f = runs_dir(repo) / f"done-{sha}.hand.json"
    return f, (json.loads(f.read_text()) if f.exists() else {})


def look(repo, sha, notes):
    f, have = looked(repo, sha)
    by_hand = [r["metric"] for r in how_we_know((repo / "GOALS.md").read_text() if (repo / "GOALS.md").exists() else "") if not r["cmd"]]
    for words, saw in notes:
        rows = [m for m in by_hand if words.lower() in m.lower()]
        if len(rows) != 1 or not saw.strip():
            sys.exit(f'fium done --by-hand "{words}": name one row checked by hand by words from its metric, then what you looked at. '
                     f"The rows: {'; '.join(by_hand) or 'none'}")
        have[rows[0]] = {"saw": saw.strip(), "change": changed(repo, sha)}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(have))


def short(cmd):
    return cmd if len(cmd) <= 60 else cmd[:57] + "..."


def done_main(a):
    global TIMEOUT
    TIMEOUT = a.timeout
    repo = Path(git(".", "rev-parse", "--show-toplevel").stdout.strip() or ".").resolve()
    branch = base_branch(repo, a.base)
    if a.start:
        sys.exit(start(repo, git(repo, "merge-base", branch, "HEAD").stdout.strip(), a.expect or ()))
    sha = git(repo, "merge-base", branch, "HEAD").stdout.strip()
    if a.by_hand:
        look(repo, sha, a.by_hand)
    said = []
    def tee(*x, **kw):
        said.append(" ".join(map(str, x)))
        a.json or print(*x, **kw)
    res = done(repo, sha, branch, a.costly, print=tee)
    code = 1 if res["blocked"] or res["hard"] or res["other_model"] or res["unmet"] else \
        3 if res["grew"] or res["pending"] or res["unmeasured"] or res["asks"] or res["unseen"] else 0
    save_verdict(repo, code, [l for l in "\n".join(said).splitlines() if not l.startswith(" ")], unmet=res["unmet"], base=sha)
    if a.json:
        print(json.dumps({"code": code, "base": sha, "holds": holds(res), "rows": res["rows"]}))
    if code:
        sys.exit(code)
    a.json or print("Nothing got worse past its cap and nothing broke: it can merge.")


# Each list done returns, as the state it leaves a change in and whose move it is: the agent's to fix, or the user's to decide.
HOLDS = [("unmet", "result not met", "agent"), ("blocked", "broke or crossed a limit", "agent"), ("other_model", "ran on another model at the base", "agent"),
         ("hard", "got worse, held hard", "agent"), ("grew", "got worse past its margin", "user"), ("pending", "costly, not run", "agent"),
         ("unmeasured", "couldn't measure", "agent"), ("unseen", "not checked by hand", "agent"), ("asks", "dropped from How we know", "user")]


def holds(res):
    # Everything keeping a change open, each with the goal and row it came from and, for a number, its before, after and cap.
    out = []
    for key, state, whose in HOLDS:
        for w in res[key]:
            v = res["verdicts"].get(w) or next((t for t in res["rows"] if w in (t["row"], t["cmd"]) or w.startswith(t["row"] + " (")), {})
            out.append({"state": {"adds": "adds code no number shows", "judge": "edits what judges it"}.get(w, state) if key == "asks" else state,
                        "what": w, "whose": whose, "goal": v.get("goal"), "row": v.get("row"), **{k: v[k] for k in ("base", "run", "cap") if k in v}})
    return out


def verdict_file(repo):
    return runs_dir(repo) / "verdicts.json"


def save_verdict(repo, code, lines, unmet=(), base=None):
    # The last verdict per checkout, kept outside the repo (K3): what a turn-end check reads when the output was filtered.
    f = verdict_file(repo)
    have = json.loads(f.read_text()) if f.exists() else {}
    have[str(Path(repo).resolve())] = {"code": code, "head": git(repo, "rev-parse", "HEAD").stdout.strip(),
                                       "at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()), "said": [l for l in lines if not l.startswith(("fium done:", "  "))][-6:],
                                       "unmet": list(unmet), "base": base}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(have))


def saved_verdict(repo):
    f = verdict_file(repo)
    return (json.loads(f.read_text()) if f.exists() else {}).get(str(Path(repo).resolve()))


def done(repo, sha, branch, costly=False, print=print):
    # Every How we know row at sha and now, printed under its goal; returns what blocks, what grew and each verdict.
    goals = (repo / "GOALS.md").read_text() if (repo / "GOALS.md").exists() else ""
    rows = how_we_know(goals)
    dirty = bool(git(repo, "status", "--porcelain").stdout.strip())
    # Read before any row runs: a bench may write into the tree.
    now_change, saw, unseen = changed(repo, sha), looked(repo, sha)[1], []
    label = {}
    for r in rows:
        label.setdefault(r["cmd"], r["metric"])
    # A row the change adds (neither its metric nor its command was in the base's table) has no base to fail at: what
    # it reads is new. Rewording one of the two keeps a row what it was.
    base_goals = git(repo, "show", f"{sha}:GOALS.md").stdout
    then = how_we_know(base_goals)
    was, ran = {r["metric"] for r in then}, {r["cmd"] for r in then if r["cmd"]}
    old = lambda r: r["metric"] in was or r["cmd"] in ran
    fresh = {r["cmd"] for r in rows if r["cmd"]} - {r["cmd"] for r in rows if old(r)}
    # A live row whose before was read (start) is held to it like any row; a new one is read like a new row.
    read = {c: x for c, x in live_before(repo, sha)[1].get("raw", {}).items() if c in label and measure(x, label[c])["metrics"]}
    for r in rows:
        if r["kind"] == "live" and (r["cmd"] in read or r["cmd"] in fresh):
            r["kind"] = None
    cmds = list(dict.fromkeys(r["cmd"] for r in rows if r["cmd"] and (not r["kind"] or r["kind"] == "costly" and costly)))
    costly = {r["cmd"] for r in rows if r["kind"] == "costly"}
    timed = lambda c, x: any(m.get("noisy", m.get("kind", "time") in NOISY) for m in measure(x, label[c])["metrics"].values())
    now = {}
    cache = runs_dir(repo) / f"done-{sha}.raw.json"
    kept = json.loads(cache.read_text()) if cache.exists() else {}
    have = {**at_base(repo, sha, [c for c in cmds if c not in read and c not in fresh], costly, timed, now), **read}
    base = {c: measure(raw, label[c]) for c, raw in have.items() if c in cmds}
    new_row = {c for c in cmds if c in fresh and c not in base}
    base.update({c: {"ok": True, "s": 0, "metrics": {}, "limits": {}} for c in new_row})
    raw = {c: now.get(c) or execute(c, repo) for c in cmds + [r["cmd"] for r in rows if r["kind"] == "live"]}
    here = {c: measure(x, label[c]) for c, x in raw.items()}
    # A change is held to the base's caps, never to ones it wrote itself (K5): a new Caps line waits on the user's word.
    caps, wrote = (parse_caps(base_goals) if base_goals else parse_caps(goals)), parse_caps(goals)
    nf = noise_file(repo)
    noise = json.loads(Path(nf).read_text()) if nf else {}
    rel = lambda name: noise.get("rel", {}).get(name, DEFAULT_REL)
    print(f"fium done: {'this tree' if dirty else 'HEAD'} against {branch} at {sha[:7]}")
    # The contract comes first: what the change set out to do, each result met once its command passes here.
    items = json.loads(contract_file(repo, sha).read_text())["items"] if contract_file(repo, sha).exists() else []
    if items:
        print("What this change set out to do")
    unmet = []
    for i in items:
        x = execute(i["cmd"], repo)
        last = (x["out"] + x["err"]).strip().splitlines()[-1:] or [""]
        print(f"  {'met' if not x['code'] else 'not met':>9}  {i['what']}" + (f": {last[0][:80]}" if x["code"] else ""))
        unmet += [i["what"]] if x["code"] else []
    # Each row shows under its goal's name from the Goals list, so nobody has to look a number up.
    titles = dict(re.findall(r"^(\d+)\.\s+\*\*(.+?)\.?\*\*", metrics_table(goals)[0], re.M))
    shown = None
    # A command's metrics show under the row whose Where names them, else whose text does, else its first row.
    owner = {}
    for c in cmds:
        users = [i for i, r in enumerate(rows) if r["cmd"] == c and r["kind"] != "live"]
        for name in {**base[c]["metrics"], **here[c]["metrics"]}:
            owner[(c, name)] = ([i for i in users if claims(name, rows[i]["where"])] or
                                [i for i in users if claims(name, rows[i]["text"])] or users)[0]
    blocked, hard, grew, pending, unmeasured, other_model, failed, verdicts, news, table = [], [], [], [], [], [], [], {}, [], []
    for r in rows:
        if r["goal"] != shown:
            print(titles.get(r["goal"], f"Goal {r['goal']}"))
            shown = r["goal"]
        print(f"  {r['metric']}")
        c = r["cmd"]
        # Where the row's number came from; a base read back from an earlier done is kept, not measured again.
        table.append({"goal": titles.get(r["goal"], f"Goal {r['goal']}"), "row": r["metric"], "cmd": c, "from": "by hand" if not c else
                      "live" if r["kind"] == "live" or c in read else "not run" if c not in here else "new" if c in new_row else
                      "kept base" if kept.get(c) == have.get(c) else "measured now"})
        if not c:
            # A row nobody can run is satisfied only by what was looked at for this change, shown here (W6).
            s = saw.get(r["metric"])
            how = r["by_hand"] or "no Run cell"
            covers = paths(r["where"])
            if not now_change:
                print(f"       {how}: nothing changed since {branch}")
            elif covers and not touched(repo, sha, covers):
                print(f"       {how}: nothing changed in {', '.join(covers)}")
            elif s:
                fresh_look = s["change"] == now_change
                print(f"       {how}{'' if fresh_look else ', before the tree changed'}: " + s["saw"].replace("\n", "\n         "))
                unseen += [] if fresh_look else [r["metric"]]
            else:
                print(f"       {how}: nothing recorded")
                unseen.append(r["metric"])
            continue
        if r["kind"] == "live":
            got = here[c]["metrics"]
            print(f"       live `{short(c)}`: " + (reading(here[c], r) + " now" if got else ("" if here[c]["ok"] else here[c]["fails"] + ", ")
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
        first = i == min(j for j, x in enumerate(rows) if x["cmd"] == c and x["kind"] != "live")
        state = ("ok" if b["ok"] else "ok now, failed at the base") if h["ok"] else h["fails"] + ("" if b["ok"] else " (failed at the base too)")
        if first and c in new_row:
            print(f"       `{short(c)}`: new row, {'ok' if h['ok'] else h['fails']}, {h['s']:g}s")
            if h["ok"] and not h["metrics"]:
                unmeasured += [f"{x['metric']} (new row printed no number)" for x in rows if x["cmd"] == c]
        elif first:
            print(f"       `{short(c)}`: {state}, {b['s']:g}s -> {h['s']:g}s")
            env = env_row(b, h)
            if env:
                print(f"     {env['verdict']:>9}  model: {change(env['base'], env['run'])}")
            if env and env["verdict"] == "not comparable":
                other_model.append(short(c))
            if not b["ok"]:
                # A command that failed at the base measured nothing to hold now against, for every row that runs it.
                why = "fails before and after" if not h["ok"] else "failed at the base"
                unmeasured += [f"{x['metric']} ({why})" for x in rows if x["cmd"] == c and x["kind"] != "live"]
        else:
            print(f"       `{short(c)}`: {state}, as above")
        if first and b["ok"] and not h["ok"]:
            # A new row's base is ok by definition, so one that fails now broke too.
            blocked.append(c)
            failed.append(short(c))
        if first:
            for n in h.get("no_number", []):
                print(f"     {'no number':>9}  {n}")
                unmeasured.append(f"{n} (`{short(c)}` wrote no number)")
        mine = [n for n in {**b["metrics"], **h["metrics"]} if owner[(c, n)] == i]
        for name in mine:
            if name not in b["metrics"]:
                print(f"     {'new':>9}  {name}: {statistics.median(h['metrics'][name]['samples']):g}")
                news.append(name)
        same = 0
        for name, m in b["metrics"].items():
            if name not in mine:
                continue
            v = judge(name, m, h["metrics"].get(name), rel(name), {**b["limits"], **h["limits"]}.get(name), noise.get("abs", {}).get(name, 0),
                      cap_for(name, m.get("kind", "time"), caps))
            verdicts[name] = {**v, "kind": m.get("kind", "time"), "dir": m.get("dir", "lower"), "goal": table[-1]["goal"], "row": r["metric"]}
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
    if unmet:
        print(f"Not done: {', '.join(unmet)} isn't met yet. Keep going until it is, or ask the user what only they can answer.")
    if blocked:
        print(f"Not done: {', '.join(blocked)} broke or crossed a limit. Fix it.")
    if other_model:
        print(f"Not done: {', '.join(other_model)} ran on another model at the base. Measure both on the same model.")
    if hard:
        print(f"Not done: {', '.join(hard)} (hard) got worse. Make it the same or better, or agree with the user it can't be without lowering quality.")
    if grew:
        print(f"{', '.join(grew)} got worse past its margin. Simplify it, or the user lets it pass.")
    # K4: what a change adds needs a better number or a new one; more passing tests isn't that number.
    asks = []
    shown_by = [n for n in news if n != "tests passing"] + [n for n, v in verdicts.items() if v["verdict"] == "better" and n != "tests passing"]
    added = added_code(repo, sha) if rows else 0
    if added >= ADDS and not shown_by:
        print(f"This change adds {added} lines of code no number shows. Add a How we know row that runs it the way the user does, "
              "from their action to what they see: each fallback, and what the screen shows after each. Use the cheapest run "
              "that gets there, headless; live: only when nothing cheaper reaches it. Ask the user to let it pass only when no row can reach it, "
              "and say in the question what the lines do and why nothing can measure them.")
        asks.append("adds")
    now, runs = {r["metric"] for r in rows}, {r["cmd"] for r in rows}
    dropped = list(dict.fromkeys(r["metric"] for r in then if r["metric"] not in now and r["cmd"] not in runs))
    if dropped:
        print(f"Dropped from How we know: {', '.join(dropped)}. A cut nothing measures isn't kept: put it back, or the user says it can go.")
        asks += dropped
    for r in rows:
        w = not old(r) and re.search(r"\b(dry|stub|fake)\b", f"{r['cmd'] or ''} {r['where']}", re.I)
        if w:
            print(f"{r['metric']}: its row says {w[1]}, so it doesn't run it the way the user does. Run the real thing, or say why it can't.")
    # What judges a change is out of its reach: a row whose command it edited, the Caps line, or a bench file it changed
    # (bench/judge, else bench/* and the baseline and noise files) is the user's to OK, or the change puts it back.
    edits = [f"{r['metric']} runs `{short(r['cmd'] or r['by_hand'])}`, was `{short(c)}`" for r in rows
             for c in [next((x["cmd"] for x in then if x["metric"] == r["metric"]), None)] if c and c != r["cmd"]]
    if wrote != caps:
        edits.append(f"the Caps line, held to the base's {caps_line(caps) if caps else 'none (all ask)'}")
    judges = globs(repo, "judge", [g for g in JUDGE if not g.startswith("test")])
    edits += [f for st, f in (l.split("\t", 1) for l in git(repo, "diff", "--name-status", "--no-renames", sha).stdout.splitlines() if "\t" in l)
              if st != "A" and any(fnmatch(f, g) for g in judges)]
    if edits:
        print(f"This change edits what judges it: {'; '.join(edits)}. The user OKs it, or put it back.")
        asks.append("judge")
    if old_caps(goals):
        print(f"GOALS.md's Caps line uses the old digits. Write it in words: {caps_line(caps)}")
    if pending and not (blocked or hard):
        print(f"Not measured yet: {', '.join(dict.fromkeys(pending))} (costly). It isn't done until they run, or the user says they needn't.")
    if unmeasured:
        print(f"Couldn't measure: {', '.join(unmeasured)}. It isn't done until they run clean, or the user says they needn't.")
        if any(u.endswith("(live: no before)") for u in unmeasured):
            print("A live row's before is read once, when the plan is frozen: fium done --start.")
    if unseen:
        print(f"Not checked by hand: {', '.join(unseen)}. List what the old one showed and every place and size it shows, look at "
              f'each one as it is now, then say what you saw: fium done --by-hand "{unseen[0]}" "<each case and what it shows>". '
              "Or the user says it needn't.")
    return {"unmet": unmet, "unseen": unseen, "blocked": blocked, "hard": hard, "grew": grew, "pending": pending, "unmeasured": unmeasured, "asks": asks,
            "other_model": other_model, "failed": failed, "verdicts": verdicts, "rows": table, "raw": {c: raw[c] for c in costly & set(cmds)}}
