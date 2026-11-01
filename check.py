"""fium check: a project against the ✓ rules in RULES.md. Each finding cites a rule id."""
import os, re, subprocess
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
    for rule, name in (("F3", "README.md"), ("F4", "GOALS.md"), ("F5", "LICENSE")):
        if not (root / name).exists():
            out.append(finding(rule, "error", name, "missing", f"copy templates/{name}"))
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
        rows = [r for r in m.group(1).splitlines() if r.startswith("|")][2:]
        for r in rows:
            cells = [c.strip() for c in r.strip("|").split("|")]
            if len(cells) < 3 or not cells[1] or not cells[-1]:
                out.append(finding("G2", "error", "GOALS.md", f"metric row without a metric or a where: {r.strip()}",
                                   "name the command or file that measures it"))
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
    titled = bool(lines) and lines[0].strip() in (f"# {name}", f"# /{name}")
    if not titled and not logo:
        out.append(finding("R1", "error", "README.md", f"first line should be '# {name}'", f"set the title to '# {name}'"))
    opener = next((l for l in lines[titled:] if l.strip()), "")
    if not (named_logo and not titled) and not re.match(rf"^/?{re.escape(name)}\b", opener, re.I):
        out.append(finding("R2", "warn", "README.md", "opener should start with the plain name and say what it does",
                           f"'{name} does X.' in one sentence"))
    for sec in ("Install", "Use"):
        if not re.search(rf"^## {sec}\b", text, re.M):
            out.append(finding("R3", "error" if sec == "Install" else "warn", "README.md", f"no '## {sec}' section", f"add ## {sec}"))
    if re.search(r"shields\.io|badge", text, re.I):
        out.append(finding("R4", "warn", "README.md", "badges", "remove badges"))
    out += readme_drift(root, name, text)
    dev = re.findall(r"^## (Development|Contributing|Architecture|Building|Build|How it works|Internals)\b", text, re.M | re.I)
    if dev:
        out.append(finding("R5", "warn", "README.md", "sections for builders, not users: " + ", ".join(dev),
                           "move build, dev and internals to AGENTS.md; the README says why it's useful and how to use it"))
    return out


IMPORT = re.compile(r"^\s*@[~./\w-]+\S*\s*$")


def check_agent_docs(root):
    out = []
    agents = root / "AGENTS.md"
    if agents.is_file() and not re.search(r"^## Test\b", agents.read_text(), re.M):
        out.append(finding("F7", "error", "AGENTS.md", "no '## Test' section", "add ## Test with the command that runs the tests"))
    for p in [agents, *sorted(root.glob("SKILL.md")), *sorted(root.glob("skills/*/SKILL.md"))]:
        if not p.is_file():
            continue
        # Fenced code may hold decorators or handles; only prose lines can be imports.
        prose = re.sub(r"^```.*?^```", "", p.read_text(), flags=re.M | re.S)
        bad = [l.strip() for l in prose.splitlines() if IMPORT.match(l)]
        if bad:
            out.append(finding("F6", "error", str(p.relative_to(root)), "@ imports: " + ", ".join(bad),
                               "inline the text, or name the file as a plain path to read; an import that stops resolving drops its text silently"))
    return out


def check_memory(root):
    # Claude names a project's folder after its path with every other character as "-".
    conf = Path(os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude").expanduser()
    mem = conf / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(root)) / "memory"
    out = []
    for p in sorted(mem.glob("*.md")) if mem.is_dir() else []:
        m = re.match(r"---\n(.*?)\n---", p.read_text(), re.S)
        if p.name != "MEMORY.md" and not (m and re.search(r"^name:", m[1], re.M) and re.search(r"^description:", m[1], re.M)):
            out.append(finding("M1", "error", str(p), "no name and description frontmatter",
                               "open with ---, name: <slug>, description: <one line>, ---"))
    return out


def own_checks(root):
    # A project's checks fium can't know about, one shell command per line, run from its root (F8).
    p = root / "bench" / "checks"
    out = []
    for cmd in [l.strip() for l in p.read_text().splitlines() if l.strip() and not l.startswith("#")] if p.is_file() else []:
        r = subprocess.run(cmd, shell=True, cwd=root, capture_output=True, text=True)
        if r.returncode:
            tail = (r.stderr or r.stdout).strip().splitlines()[-1:] or [f"exit {r.returncode}"]
            out.append(finding("F8", "error", "bench/checks", f"{cmd}: {tail[0]}", f"run it in {root.name} and fix what it reports"))
    return out


FENCE = re.compile(r"^```.*?^```", re.M | re.S)
CODE_EXT = {".py", ".js", ".mjs", ".cjs", ".ts", ".sh", ".swift", ".go", ".rs", ".lua", ""}
SKIP_DIRS = {".git", "node_modules", "test", "tests", "docs", ".build", "dist", "build", "vendor"}


def words_in(p):
    # What a CLI can be called with: quoted literals (argparse names, case "verb") and shell `verb)` arms.
    src = p.read_text(errors="replace")
    return set(re.findall(r"[\"'`](-{0,2}\w[\w-]*)[\"'`=]", src)) | set(re.findall(r"^\s*\"?([\w-]+)\"?\)", src, re.M))


def cli_words(root, name, shown):
    extra = root / "bench" / "readme-cli"
    words = set(extra.read_text().split()) if extra.is_file() else set()
    for p in (root / name, root / "bin" / name):
        words |= words_in(p) if p.is_file() else set()
    if shown <= words:
        return words
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS and not x.startswith(".")]
        words |= {w for f in files if Path(f).suffix in CODE_EXT and Path(d, f).stat().st_size < 1_000_000 for w in words_in(Path(d, f))}
    return words


def readme_drift(root, name, text):
    # R6: the README says only what a user sees and types, and what it shows under Use still exists.
    out, prose = [], FENCE.sub("", text)
    env = sorted(set(re.findall(r"\$?\b[A-Z][A-Z0-9]*_[A-Z0-9_]+\b", prose)))
    if env:
        out.append(finding("R6", "error", "README.md", "names env vars: " + ", ".join(env),
                           "say what the user does instead, or move the variable to AGENTS.md"))
    use = re.search(r"^## Use\b(.*?)(?=^## |\Z)", text, re.M | re.S)
    shown = set()
    for block in re.findall(r"^```.*?\n(.*?)^```", use[1] if use else "", re.M | re.S):
        for l in block.splitlines():
            words = l.strip().removeprefix("$ ").split()
            if words and re.fullmatch(rf"(\S*/)?{re.escape(name)}", words[0]):
                args = [w.split("=")[0] for w in words[1:]]
                shown |= {w for w in args if w.startswith("-")} | ({args[0]} if args and re.fullmatch(r"[a-z][\w-]*", args[0]) else set())
    missing = sorted(shown - cli_words(root, name, shown)) if shown else []
    if missing:
        out.append(finding("R6", "error", "README.md", "Use shows what the CLI doesn't have: " + ", ".join(missing),
                           "update the README, or list them in bench/readme-cli if the source names them another way"))
    for what, rx in (("timings", r"\b\d+(?:\.\d+)? ?(?:ms|s|Hz|minutes?)\b"), ("source paths", r"\bSources/|\b[\w/.-]+\.(?:swift|py)\b")):
        hits = sorted(set(re.findall(rx, prose)))
        if hits:
            out.append(finding("R6", "warn", "README.md", f"{what} in prose: " + ", ".join(hits),
                               "describe what the user sees; numbers and internals go stale in AGENTS.md or the code"))
    return out


DESIGN_SECTIONS = [("overview", "brand & style"), ("colors",), ("typography",), ("layout", "layout & spacing"),
                   ("elevation & depth", "elevation"), ("shapes",), ("components",), ("do's and don'ts",)]
YAML_LINE = re.compile(r"( *)([\w.-]+|\"[^\"]*\"|'[^']*'):(?:\s+(.*))?")


def check_design(root):
    # D1: Google's DESIGN.md (spec 0.4.0) in the YAML subset it uses: nested keys, scalar values, {path} refs.
    p = root / "DESIGN.md"
    if not p.is_file():
        return []
    text = p.read_text()
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not m:
        return [finding("D1", "error", "DESIGN.md", "no YAML front matter", "open with ---, the tokens, --- (templates/DESIGN.md)")]
    values, stack, bad, refs, lists = {}, [], [], [], set()
    for n, l in enumerate(m[1].splitlines(), 2):
        if not l.strip() or l.lstrip().startswith("#"):
            continue
        y = YAML_LINE.fullmatch(l.rstrip())
        if not y:
            if re.fullmatch(r" +- \S.*", l) and stack:
                lists.add(".".join(k for _, k in stack))
            else:
                bad.append(str(n))
            continue
        stack = [s for s in stack if s[0] < len(y[1])] + [(len(y[1]), y[2].strip("\"'"))]
        values[".".join(k for _, k in stack)] = re.sub(r"\s+#.*", "", y[3] or "").strip()
        refs += re.findall(r"\{([\w.-]+)\}", y[3] or "")
    paths, out = set(values), []
    # Themes: `themes: [light, dark]`, and a key ending in -<theme> overrides its base key.
    themes = re.findall(r"[\w-]+", values.get("themes", ""))
    for p in sorted(paths):
        base, _, t = p.rpartition("-")
        if not base:
            continue
        if t in themes and base not in paths:
            out.append(finding("D1", "error", "DESIGN.md", f"{p} has no base", f"add {base}, or rename the key"))
        elif base in paths and t in ("light", "dark") and t not in themes:
            out.append(finding("D1", "error", "DESIGN.md", f"{p}: theme {t} isn't in themes", f"list it: themes: [..., {t}]"))
    if "omitted" in values and not (values["omitted"].startswith("[") or not values["omitted"] and "omitted" in lists):
        out.append(finding("D1", "error", "DESIGN.md", "omitted isn't a list", "omitted: [\"--a-*\"], or one '- item' per line"))
    if bad:
        out.append(finding("D1", "error", "DESIGN.md", "front matter lines that don't parse: " + ", ".join(bad),
                           "each line is 'key: value' or 'key:' with deeper keys under it"))
    broken = sorted({r for r in refs if r not in paths})
    if broken:
        out.append(finding("D1", "error", "DESIGN.md", "refs that don't resolve: " + ", ".join(f"{{{r}}}" for r in broken),
                           "define the token or fix the ref"))
    order = [i for h in re.findall(r"^## (.+?)\s*$", FENCE.sub("", text[m.end():]), re.M)
             for i, names in enumerate(DESIGN_SECTIONS) if h.lower() in names]
    if order != sorted(set(order)):
        out.append(finding("D1", "error", "DESIGN.md", "sections out of the spec's order or repeated",
                           "Overview, Colors, Typography, Layout, Elevation & Depth, Shapes, Components, Do's and Don'ts"))
    return out


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
    return (check_files(root) + check_goals(root) + check_readme(root) + check_agent_docs(root) + check_memory(root)
            + check_design(root) + check_tested_fixes(root))

