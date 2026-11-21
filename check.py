"""fium check: a project against the ✓ rules in RULES.md. Each finding cites a rule id."""
import re, subprocess
from fnmatch import fnmatch
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
    ignore = root / ".gitignore"
    if not ignore.exists():
        out.append(finding("F1", "error", ".gitignore", "missing", "copy templates/.gitignore"))
    elif ".DS_Store" not in ignore.read_text():
        out.append(finding("F1", "error", ".gitignore", "lets Finder's .DS_Store into git", "add a .DS_Store line"))
    return out


# Header names fium knows for the metrics table's Where and Run columns; any other header falls back to the
# template's positions (Goal | Metric | Where | Run).
WHERE_COLS = {"where", "dónde", "donde"}
RUN_COLS = {"run", "correr", "comando", "command"}


def metrics_table(text):
    # GOALS.md's metrics table, found by shape so its headings may be in any language: the first Markdown table after
    # the numbered goals, with any table lines after it up to the next heading. Returns the text before it, holding the
    # goals, and the table's lines.
    lines = text.splitlines()
    first = next((i for i, l in enumerate(lines) if re.match(r"\d+\. ", l)), 0)
    start = next((i for i in range(first, len(lines)) if lines[i].startswith("|")), None)
    if start is None:
        return text, []
    stop = next((i for i in range(start, len(lines)) if lines[i].startswith("## ")), len(lines))
    return "\n".join(lines[:start]), [l for l in lines[start:stop] if l.startswith("|")]


def columns(head):
    # The Where and Run columns' indexes in a header's lowercased cells, by name, else by the template's position.
    def col(names, pos):
        named = [i for i, c in enumerate(head) if c in names]
        return named[0] if named else (pos if len(head) > pos and not set(head) & (WHERE_COLS | RUN_COLS) else None)
    return col(WHERE_COLS, 2), col(RUN_COLS, 3)


def check_goals(root):
    p = root / "GOALS.md"
    if not p.exists():
        return []
    text = p.read_text()
    out = []
    before, table = metrics_table(text)
    goals = set(re.findall(r"^(\d+)\. ", before, re.M))
    if table:
        covered = {c.split("|")[1].strip() for c in table}
        for g in sorted(goals - covered):
            out.append(finding("G2", "error", "GOALS.md", f"goal {g} has no row in the metrics table", "add: | {g} | metric | command or file |".replace("{g}", g)))
        head = [c.strip().lower() for c in table[0].strip().strip("|").split("|")]
        run = columns(head)[1]
        if run is None:
            out.append(finding("G2", "warn", "GOALS.md", "the metrics table has no Run column, so fium done can't measure it",
                               "add | Run | to each row: `the command`, live: `a command on live state`, or by hand"))
        for r in table[2:]:
            cells = [c.strip() for c in r.strip().strip("|").split("|")]
            if len(cells) < 3 or not cells[1] or not cells[2]:
                out.append(finding("G2", "error", "GOALS.md", f"metric row without a metric or a where: {r.strip()}",
                                   "name the command or file that measures it"))
            elif run is not None and not (cells[run] if len(cells) > run else ""):
                out.append(finding("G2", "warn", "GOALS.md", f"row without a Run cell: {r.strip()}",
                                   "`the command`, live: `a command on live state`, or by hand"))
    elif goals:
        out.append(finding("G2", "error", "GOALS.md", "no metrics table after the goals",
                           "add one: | Goal | Metric | Where | Run | (templates/GOALS.md)"))
    return out


def repo_name(root):
    url = git(root, "remote", "get-url", "origin").stdout.strip()
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
    dev = re.findall(r"^## (Development|Contributing|Architecture|Building|Build|How it works|Internals)\b", text, re.M | re.I)
    if dev:
        out.append(finding("R3", "warn", "README.md", "sections for builders, not users: " + ", ".join(dev),
                           "move build, dev and internals to AGENTS.md; the README says why it's useful and how to use it"))
    return out


def check_agent_docs(root):
    out = []
    agents = root / "AGENTS.md"
    # A project with goals tells its agents how a change is judged done, so no session falls back on an older way.
    goals = root / "GOALS.md"
    if agents.is_file() and goals.is_file() and metrics_table(goals.read_text())[1]:
        text = agents.read_text()
        old = sorted({w for t in re.findall(r"fium compare[^\n]*?(--since|--price)|(--house)\b|^(Price:)", text, re.M) for w in t if w})
        if old:
            out.append(finding("K3", "warn", "AGENTS.md", f"judges a change the old way ({', '.join(old)})",
                               "say a change is done when `fium done` says so, and drop the old way"))
        elif "fium done" not in text:
            out.append(finding("K3", "warn", "AGENTS.md", "doesn't say a change is judged with fium done",
                               "add where it says how to test: a change is done when `fium done` says so"))
    return out


def own_checks(root):
    # A project's checks fium can't know about, one shell command per line, run from its root (F4).
    p = root / "bench" / "checks"
    out = []
    changed = None
    for cmd in [l.strip() for l in p.read_text().splitlines() if l.strip() and not l.startswith("#")] if p.is_file() else []:
        # "when <glob> …: <command>" runs only when the change since the base branch touches a file a glob matches.
        when = re.match(r"when\s+(.+?):\s+(.+)", cmd)
        if when:
            if changed is None:
                sha = git(root, "merge-base", base_branch(root), "HEAD").stdout.strip()
                changed = git(root, "diff", "--name-only", sha).stdout.split() + git(root, "ls-files", "--others", "--exclude-standard").stdout.split()
            if not any(fnmatch(f, g) for f in changed for g in when[1].split()):
                continue
            cmd = when[2]
        r = subprocess.run(cmd, shell=True, cwd=root, capture_output=True, text=True)
        if r.returncode:
            tail = (r.stderr or r.stdout).strip().splitlines()[-1:] or [f"exit {r.returncode}"]
            out.append(finding("F4", "error", "bench/checks", f"{cmd}: {tail[0]}", f"run it in {root.name} and fix what it reports"))
    return out


CODE_EXT = {".py", ".js", ".mjs", ".cjs", ".ts", ".sh", ".swift", ".go", ".rs", ".lua", ""}
SKIP_DIRS = {".git", "node_modules", "test", "tests", "docs", ".build", "dist", "build", "vendor"}


def repos_under(base):
    # A hidden folder is never one of the user's repos: it's a copy, like the base fium done checks out beside a repo.
    return sorted({d.resolve() for d in Path(base).expanduser().iterdir() if (d / ".git").exists() and not d.name.startswith(".")})


def git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True)


def base_branch(repo, base=None):
    return base or next((b for b in ("main", "master") if not git(repo, "rev-parse", "-q", "--verify", b).returncode), "HEAD")


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

