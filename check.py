"""fium check: a project against the ✓ rules in RULES.md. Each finding cites a rule id."""
import re, subprocess
from pathlib import Path


def finding(rule, level, file, msg, fix):
    return {"rule": rule, "level": level, "file": file, "msg": msg, "fix": fix}


def check_files(root):
    out = []
    if not (root / "AGENTS.md").exists():
        fix = "git mv AGENT.md AGENTS.md" if (root / "AGENT.md").exists() else "write AGENTS.md (templates/AGENTS.md)"
        out.append(finding("F1", "error", "AGENTS.md", "missing", fix))
    claude = root / "CLAUDE.md"
    if not (claude.is_symlink() and claude.readlink().name == "AGENTS.md"):
        out.append(finding("F2", "error", "CLAUDE.md", "not a symlink to AGENTS.md",
                           "move anything unique into AGENTS.md, then: ln -sf AGENTS.md CLAUDE.md"))
    for name in ("README.md", "GOALS.md", "LICENSE"):
        if not (root / name).exists():
            out.append(finding("F1", "error", name, "missing", f"copy templates/{name}"))
    return out


GOAL_SECTIONS = [
    ("purpose", r"^## What .+ is for"),
    ("never traded", r"^## .*never trad"),
    ("goals", r"^## Goals"),
    ("how we know", r"^## How we know"),
    ("non-goals", r"^## Non-goals"),
]


def check_goals(root):
    p = root / "GOALS.md"
    if not p.exists():
        return []
    text = p.read_text()
    out = []
    missing = [n for n, rx in GOAL_SECTIONS if not re.search(rx, text, re.M | re.I)]
    if missing:
        out.append(finding("G1", "error", "GOALS.md", "missing sections: " + ", ".join(missing), "follow templates/GOALS.md"))
    m = re.search(r"^## How we know\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    goals = set(re.findall(r"^(\d+)\. ", text.split("## How we know")[0], re.M))
    if m:
        covered = {c.split("|")[1].strip() for c in m.group(1).splitlines() if c.startswith("|")}
        for g in sorted(goals - covered):
            out.append(finding("G2", "error", "GOALS.md", f"goal {g} has no row in How we know", "add: | {g} | metric | command or file |".replace("{g}", g)))
        table = [r for r in m.group(1).splitlines() if r.startswith("|")]
        head = [c.strip().lower() for c in table[0].strip().strip("|").split("|")] if table else []
        if table and "run" not in head:
            out.append(finding("G2", "warning", "GOALS.md", "How we know has no Run column, so fium done can't measure it",
                               "add | Run | to each row: `the command`, live: `a command on live state`, or by hand"))
        for r in table[2:]:
            cells = [c.strip() for c in r.strip().strip("|").split("|")]
            if len(cells) < 3 or not cells[1] or not cells[2]:
                out.append(finding("G2", "error", "GOALS.md", f"metric row without a metric or a where: {r.strip()}",
                                   "name the command or file that measures it"))
            elif "run" in head and not (cells[head.index("run")] if len(cells) > head.index("run") else ""):
                out.append(finding("G2", "warning", "GOALS.md", f"row without a Run cell: {r.strip()}",
                                   "`the command`, live: `a command on live state`, or by hand"))
    return out


def repo_name(root):
    import subprocess
    url = subprocess.run(["git", "-C", str(root), "remote", "get-url", "origin"], capture_output=True, text=True).stdout.strip()
    return (url.rstrip("/").split("/")[-1].removesuffix(".git") if url else root.name).lower()


def check_readme(root):
    p = root / "README.md"
    if not p.exists():
        return []
    text = p.read_text()
    name = repo_name(root)
    out = []
    lines = text.splitlines()
    # A logo (HTML or an image) may open the README; the title, if any, follows it.
    logo = next((i for i, l in enumerate(lines) if not re.match(r"\s*(<|!\[|$)", l)), len(lines))
    # A logo whose alt text is the name already says it, so the opener after it need not.
    named_logo = re.search(rf'alt="/?{re.escape(name)}"|!\[/?{re.escape(name)}\]', "\n".join(lines[:logo]), re.I)
    lines = lines[logo:]
    titled = bool(lines) and lines[0].startswith("# ")
    opener = next((l for l in lines[titled:] if l.strip()), "")
    if not (named_logo and not titled) and not re.match(rf"^/?{re.escape(name)}\b", opener, re.I):
        out.append(finding("R1", "warn", "README.md", "opener should start with the plain name and say what it does",
                           f"'{name} does X.' in one sentence"))
    for sec in ("Install", "Use"):
        if not re.search(rf"^## {sec}\b", text, re.M):
            out.append(finding("R2", "error" if sec == "Install" else "warn", "README.md", f"no '## {sec}' section", f"add ## {sec}"))
    dev = re.findall(r"^## (Development|Contributing|Architecture|Building|Build|How it works|Internals)\b", text, re.M | re.I)
    if dev:
        out.append(finding("R3", "warn", "README.md", "sections for builders, not users: " + ", ".join(dev),
                           "move build, dev and internals to AGENTS.md; the README says why it's useful and how to use it"))
    return out


def check_agent_docs(root):
    out = []
    agents = root / "AGENTS.md"
    if agents.is_file() and not re.search(r"^## Test\b", agents.read_text(), re.M):
        out.append(finding("F3", "error", "AGENTS.md", "no '## Test' section", "add ## Test with the command that runs the tests"))
    # A project with goals tells its agents how a change is judged done, so no session falls back on an older way.
    goals = root / "GOALS.md"
    if agents.is_file() and goals.is_file() and re.search(r"^## How we know", goals.read_text(), re.M):
        text = agents.read_text()
        old = sorted(set(re.findall(r"fium compare[^\n]*?(--since|--price)|(--house)\b|^(Price:)", text, re.M)) - {("", "", "")})
        old = sorted({w for t in old for w in t if w})
        if old:
            out.append(finding("K3", "warning", "AGENTS.md", f"judges a change the old way ({', '.join(old)})",
                               "say a change is done when `fium done` says so, and drop the old way"))
        elif "fium done" not in text:
            out.append(finding("K3", "warning", "AGENTS.md", "doesn't say a change is judged with fium done",
                               "add under ## Bench or ## Test: a change is done when `fium done` says so"))
    return out


def own_checks(root):
    # A project's checks fium can't know about, one shell command per line, run from its root (F4).
    p = root / "bench" / "checks"
    out = []
    for cmd in [l.strip() for l in p.read_text().splitlines() if l.strip() and not l.startswith("#")] if p.is_file() else []:
        r = subprocess.run(cmd, shell=True, cwd=root, capture_output=True, text=True)
        if r.returncode:
            tail = (r.stderr or r.stdout).strip().splitlines()[-1:] or [f"exit {r.returncode}"]
            out.append(finding("F4", "error", "bench/checks", f"{cmd}: {tail[0]}", f"run it in {root.name} and fix what it reports"))
    return out


CODE_EXT = {".py", ".js", ".mjs", ".cjs", ".ts", ".sh", ".swift", ".go", ".rs", ".lua", ""}
SKIP_DIRS = {".git", "node_modules", "test", "tests", "docs", ".build", "dist", "build", "vendor"}


def git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True)


def check_tested_fixes(root, n=20):
    # W2 asks for the failing test first; git can only see whether a fix shipped with any test at all.
    log = git(root, "log", "--no-merges", f"-{n}", "--name-only", "--format=%x00%h %s").stdout
    out = []
    for entry in log.split("\0")[1:]:
        head, *files = [l for l in entry.splitlines() if l]
        if not re.search(r"\bfix(e[sd])?\b", head, re.I):
            continue
        tested = any({"test", "tests"} & set(Path(f).parts) or "test" in Path(f).name for f in files)
        code = any(Path(f).suffix in CODE_EXT and not SKIP_DIRS & set(Path(f).parts) for f in files)
        if code and not tested:
            out.append(finding("W2", "warn", "git log", f"{head}: no test changed",
                               "land a fix with a test that fails on the bug without it"))
    return out


def check(root):
    root = Path(root).resolve()
    return check_files(root) + check_goals(root) + check_readme(root) + check_agent_docs(root) + check_tested_fixes(root)

