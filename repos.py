"""fium survey, status, grep and new: the repos under a folder, read at each one's base, and new ones from the templates."""
import json, re, subprocess, sys
from pathlib import Path

from check import check, git
from compare import RUNS


HOME = Path(__file__).resolve().parent
SURVEYED = ("AGENTS.md", "GOALS.md", "README.md")


def headings(text):
    return {h.strip().lower() for h in re.findall(r"^## (.+)$", text, re.M)}


def survey(base, min_repos=3):
    repos = sorted(d for d in Path(base).expanduser().iterdir() if (d / ".git").exists())
    ids = re.findall(r"^- \*\*([A-Z]\d+)", (HOME / "RULES.md").read_text(), re.M)
    # A template heading's NAME matches any project name.
    known = {f: [re.compile("^" + re.escape(h).replace("name", ".+") + "$") for h in headings((HOME / "templates" / f).read_text())]
             for f in SURVEYED}
    failures, adds, cited, passing = {}, {f: {} for f in SURVEYED}, {}, 0
    for d in repos:
        fs = check(d)
        passing += not any(f["level"] == "error" for f in fs)
        for r in {f["rule"] for f in fs}:
            failures[r] = failures.get(r, 0) + 1
        for f in SURVEYED:
            p = d / f
            for h in headings(p.read_text()) if p.is_file() else ():
                if not any(rx.match(h) for rx in known[f]):
                    adds[f][h] = adds[f].get(h, 0) + 1
        log = subprocess.run(["git", "-C", str(d), "log", "--format=%B"], capture_output=True, text=True).stdout
        for rid in ids:
            if re.search(rf"\b{rid}\b", log):
                cited[rid] = cited.get(rid, 0) + 1
    drift = {f: {h: n for h, n in sorted(hs.items(), key=lambda x: -x[1]) if n >= min_repos} for f, hs in adds.items()}
    return {"repos": len(repos), "passing": passing,
            "failures": dict(sorted(failures.items(), key=lambda x: -x[1])),
            "drift": {f: hs for f, hs in drift.items() if hs},
            "cited": dict(sorted(cited.items(), key=lambda x: -x[1])),
            "uncited": [r for r in ids if r not in cited]}


def survey_main(a):
    s = survey(a.path, a.min)
    if a.json:
        return print(json.dumps(s))
    print(f"{s['passing']}/{s['repos']} repos pass fium check")
    for label, d in [("repos failing each rule", s["failures"]), ("repos citing each rule", s["cited"]),
                     *((f"{f} sections the template lacks", hs) for f, hs in s["drift"].items())]:
        print(f"{label}: " + (", ".join(f"{k} {n}" for k, n in d.items()) or "none"))
    print("never cited: " + (", ".join(s["uncited"]) or "none"))


def new(name):
    # The templates with NAME filled in, a git repo, and CLAUDE.md -> AGENTS.md (F1-F5). DESIGN.md is only for a UI (D1).
    root = Path(name).resolve()
    if root.exists():
        sys.exit(f"fium new: {root} exists; pick another name or bring it in with fium check")
    root.mkdir(parents=True)
    for src in [*(HOME / "templates").iterdir(), HOME / "LICENSE"]:
        if src.name != "DESIGN.md":
            dst = root / ("bench/baseline.json" if src.name == "baseline.json" else src.name)
            dst.parent.mkdir(exist_ok=True)
            dst.write_text(src.read_text().replace("NAME", root.name))
    (root / "CLAUDE.md").symlink_to("AGENTS.md")
    git(root, "init", "-q")
    print(f"{root}: write GOALS.md first, then the README (SKILL.md)")



def repos_under(base):
    return sorted({d.resolve() for d in Path(base).expanduser().iterdir() if (d / ".git").exists()})


def worktrees(repo):
    # [(path, branch)] from git worktree list; the first is the main checkout, whose branch is the base.
    out, path = [], None
    for l in git(repo, "worktree", "list", "--porcelain").stdout.splitlines():
        if l.startswith("worktree "):
            path = str(Path(l[9:]).resolve())
        elif l.startswith("branch "):
            out.append((path, l[18:]))
        elif l == "detached":
            out.append((path, None))
    return out


def test_at(path):
    # The first code block under AGENTS.md's ## Test (F7), run where the branch is checked out.
    m = re.search(r"^## Test\n.*?```\w*\n(.*?)```", (Path(path) / "AGENTS.md").read_text(), re.M | re.S) \
        if (Path(path) / "AGENTS.md").exists() else None
    if not m:
        return {"skipped": "no ## Test command in AGENTS.md"}
    cmds = [l for l in m.group(1).splitlines() if l.strip() and not l.startswith("#")]
    code = 0
    for c in cmds:
        code = subprocess.run(c, shell=True, cwd=path, capture_output=True, timeout=900).returncode
        if code:
            break
    return {"exit": code, "commit": git(path, "rev-parse", "HEAD").stdout.strip(), "ran": cmds}


def status(base, campaign=None):
    res = {}
    for repo in repos_under(base):
        wts = worktrees(repo)
        head = wts[0][1] if wts else None
        mine = (campaign or {}).get(repo.name, [])
        wt_of = {b: p for p, b in wts[1:] if b}
        branches = {}
        for b in git(repo, "for-each-ref", "--format=%(refname:short)", "refs/heads/").stdout.split():
            if b == head:
                continue
            ahead = int(git(repo, "rev-list", "--count", f"{head}..{b}").stdout or 0) if head else 0
            info = {"merged": True} if head and not ahead else {"merged": False, "ahead": ahead}
            if b in wt_of:
                info["worktree"] = wt_of[b]
            if b in mine and not info["merged"]:
                info["test"] = test_at(wt_of[b]) if b in wt_of else {"skipped": "no worktree; check the branch out to test it"}
            branches[b] = info
        cleanup = [c for b in mine if branches.get(b, {}).get("merged") for c in
                   ([f"git -C {repo} worktree remove {branches[b]['worktree']}"] if "worktree" in branches[b] else [])
                   + [f"git -C {repo} branch -d {b}"]]
        dirty = len(git(repo, "status", "--porcelain").stdout.splitlines())
        res[repo.name] = {"base": head, "dirty": dirty, "branches": branches, "cleanup": cleanup}
    return res


def status_main(a):
    camp = None
    if a.campaign:
        p = RUNS.parent / "campaigns" / f"{a.campaign}.json"
        if not p.exists():
            sys.exit(f"fium status: no campaign at {p}; write {{\"repos\": {{repo: [branch, ...]}}}} there")
        camp = json.load(open(p))["repos"]
    res = status(a.path, camp)
    if a.json:
        return print(json.dumps(res))
    for name, r in res.items():
        print(f"{name} ({r['base'] or 'detached'})" + (f": {r['dirty']} dirty" if r["dirty"] else ""))
        for b, i in r["branches"].items():
            t = i.get("test", {})
            test = (f"  test {'ok' if t['exit'] == 0 else 'exit ' + str(t['exit'])} at {t['commit'][:7]}" if "exit" in t
                    else f"  test skipped: {t['skipped']}" if t else "")
            print(f"  {b}: {'merged' if i['merged'] else '+' + str(i['ahead'])}" + (f"  {i['worktree']}" if "worktree" in i else "") + test)
    cleanup = [c for r in res.values() for c in r["cleanup"]]
    if cleanup:
        print("clean up the campaign's merged branches:\n" + "\n".join(f"  {c}" for c in cleanup))


def grep_main(a):
    hit = False
    for repo in repos_under(a.path):
        wts = worktrees(repo)
        head = wts[0][1] if wts else "HEAD"
        r = git(repo, "grep", "-n", "-E", a.pattern, head)
        for l in r.stdout.splitlines():
            hit = True
            print(f"{repo.name} {l}")
    sys.exit(0 if hit else 1)

