import os, re, subprocess, sys, tempfile, unittest, json
from pathlib import Path

FIUM = Path(__file__).resolve().parent.parent / "fium"
# fium compare keeps runs under FIUM_HOME; the suite never writes to the real ~/.fium.
os.environ["FIUM_HOME"] = tempfile.mkdtemp()

GOALS = """# demo: goals

## What demo is for
Things.

## Never traded
- Nothing breaks.

## Goals, in priority order
1. **Fast.**

## How we know
| Goal | Metric | Where |
|---|---|---|
| 1 | p50 per call | `bench/baseline.json` |

## Non-goals
- Everything else.
"""

README = """# demo

demo does one thing well.

## Install
```bash
make install
```

## Use
Run it.
"""


AGENTS = "# demo\n\n## Test\n```bash\nmake test\n```\n"


def make(root, **over):
    files = {"AGENTS.md": AGENTS, "README.md": README, "GOALS.md": GOALS, "LICENSE": "x\n"}
    files.update(over)
    for name, body in files.items():
        if body is None:
            continue
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    if "CLAUDE.md" not in over:
        os.symlink("AGENTS.md", root / "CLAUDE.md")
    (root / "test").mkdir(exist_ok=True)


def check(root, env=None):
    r = subprocess.run([sys.executable, str(FIUM), "check", "--json", str(root)], capture_output=True, text=True,
                       env={**os.environ, **(env or {})})
    return r.returncode, json.loads(r.stdout)


def rules(findings, level=None):
    return {f["rule"] for f in findings if level is None or f["level"] == level}


class Check(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "demo"
        self.root.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def test_good_repo_passes(self):
        make(self.root)
        code, f = check(self.root)
        self.assertEqual(code, 0, f)
        self.assertEqual(f, [])

    def test_missing_files(self):
        make(self.root, **{"GOALS.md": None, "LICENSE": None, "README.md": None})
        code, f = check(self.root)
        self.assertEqual(code, 1)
        self.assertTrue({"F3", "F4", "F5"} <= rules(f, "error"))

    def test_claude_must_be_symlink(self):
        make(self.root, **{"CLAUDE.md": "See [AGENTS.md](./AGENTS.md).\n"})
        code, f = check(self.root)
        self.assertEqual(code, 1)
        hit = [x for x in f if x["rule"] == "F2"][0]
        self.assertIn("ln -sf AGENTS.md CLAUDE.md", hit["fix"])

    def test_agent_md_singular(self):
        make(self.root, **{"AGENTS.md": None, "AGENT.md": "# x\n", "CLAUDE.md": "x"})
        _, f = check(self.root)
        hit = [x for x in f if x["rule"] == "F1"][0]
        self.assertIn("git mv AGENT.md AGENTS.md", hit["fix"])

    def test_goals_sections(self):
        make(self.root, **{"GOALS.md": "# demo: goals\n\n## Goals\n1. x\n"})
        code, f = check(self.root)
        self.assertEqual(code, 1)
        self.assertIn("G1", rules(f, "error"))

    def test_never_traded_heading_variants(self):
        make(self.root, **{"GOALS.md": GOALS.replace("## Never traded", "## Constraints (never traded)")})
        _, f = check(self.root)
        self.assertNotIn("G1", rules(f))

    def test_metric_row_needs_where(self):
        make(self.root, **{"GOALS.md": GOALS.replace("| `bench/baseline.json` |", "|  |")})
        _, f = check(self.root)
        self.assertIn("G2", rules(f, "error"))

    def test_readme_title_and_opener(self):
        make(self.root, **{"README.md": "# /Demo\n\n`demo` is a thing.\n\n## Install\nx\n"})
        _, f = check(self.root)
        self.assertTrue({"R1", "R2"} <= rules(f))

    def test_readme_install_and_badges(self):
        make(self.root, **{"README.md": "# demo\n\ndemo does X. ![b](https://img.shields.io/x)\n"})
        _, f = check(self.root)
        self.assertTrue({"R3", "R4"} <= rules(f))

    def test_all_scans_git_repos(self):
        make(self.root)
        subprocess.run(["git", "init", "-q", str(self.root)])
        (Path(self.tmp.name) / "notarepo").mkdir()
        r = subprocess.run([sys.executable, str(FIUM), "check", "--json", "--all", self.tmp.name], capture_output=True, text=True)
        out = json.loads(r.stdout)
        self.assertEqual(list(out), ["demo"])

    def test_all_runs_each_projects_own_checks(self):
        make(self.root, **{"bench/checks": "# doc budgets\ntrue\nsh -c 'echo over budget >&2; exit 1'\n"})
        subprocess.run(["git", "init", "-q", str(self.root)])
        r = subprocess.run([sys.executable, str(FIUM), "check", "--json", "--all", self.tmp.name], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        hits = [x for x in json.loads(r.stdout)["demo"] if x["rule"] == "F8"]
        self.assertEqual(len(hits), 1)
        self.assertIn("over budget", hits[0]["msg"])
        (self.root / "bench" / "checks").write_text("true\n")
        r = subprocess.run([sys.executable, str(FIUM), "check", "--json", "--all", self.tmp.name], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_every_goal_needs_a_row(self):
        make(self.root, **{"GOALS.md": GOALS.replace("1. **Fast.**", "1. **Fast.**\n2. **Small.**")})
        _, f = check(self.root)
        self.assertTrue(any(x["rule"] == "G2" and "goal 2" in x["msg"] for x in f))

    def test_use_section_required(self):
        make(self.root, **{"README.md": README.split("## Use")[0]})
        _, f = check(self.root)
        self.assertIn("R3", rules(f, "error"))

    def test_a_logo_block_may_open_the_readme(self):
        logo = '<p align="center">\n  <picture>\n    <source srcset="d.svg">\n    <img src="l.svg" alt="demo">\n  </picture>\n</p>\n\n'
        make(self.root)
        for readme in (logo + README, logo + README.split("\n", 2)[2], "![demo](logo.png)\n\n" + README):
            (self.root / "README.md").write_text(readme)
            _, f = check(self.root)
            self.assertFalse({"R1", "R2"} & rules(f), readme)
        (self.root / "README.md").write_text(logo + "Some tagline.\n\n## Install\nx\n\n## Use\ny\n")
        self.assertIn("R2", rules(check(self.root)[1]))

    def test_slash_title_allowed(self):
        make(self.root, **{"README.md": README.replace("# demo", "# /demo")})
        _, f = check(self.root)
        self.assertNotIn("R1", rules(f))

    def test_build_and_internals_sections_warn(self):
        make(self.root, **{"README.md": README + "\n## Development\nnpm run build\n\n## Architecture\nx\n"})
        code, f = check(self.root)
        self.assertEqual(code, 0)
        self.assertIn("R5", rules(f, "warn"))

    def test_agent_docs_have_no_imports(self):
        make(self.root, **{"AGENTS.md": AGENTS + "@docs/style.md\n", "skills/demo/SKILL.md": "# x\n  @~/notes.md\n```\n@decorator\n```\n"})
        code, f = check(self.root)
        self.assertEqual(code, 1)
        hits = sorted(x["file"] for x in f if x["rule"] == "F6")
        self.assertEqual(hits, ["AGENTS.md", "skills/demo/SKILL.md"])
        self.assertIn("inline", [x for x in f if x["rule"] == "F6"][0]["fix"])

    def test_agents_md_has_a_test_section(self):
        make(self.root, **{"AGENTS.md": "# demo\n\n## Build\nmake\n"})
        code, f = check(self.root)
        self.assertEqual(code, 1)
        self.assertIn("F7", rules(f, "error"))

    def test_memory_files_carry_name_and_description(self):
        make(self.root)
        conf = Path(self.tmp.name) / "claude"
        mem = conf / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(self.root.resolve())) / "memory"
        mem.mkdir(parents=True)
        (mem / "MEMORY.md").write_text("- [a](a.md) — index\n")
        (mem / "good.md").write_text("---\nname: good\ndescription: fine\nmetadata:\n  type: user\n---\nbody\n")
        (mem / "bad.md").write_text("# Decisions\nname: not frontmatter\n")
        code, f = check(self.root, {"CLAUDE_CONFIG_DIR": str(conf)})
        self.assertEqual(code, 1)
        hits = [x for x in f if x["rule"] == "M1"]
        self.assertEqual([Path(x["file"]).name for x in hits], ["bad.md"])

    def test_new_project_passes_check(self):
        r = subprocess.run([sys.executable, str(FIUM), "new", "zebra"], capture_output=True, text=True, cwd=self.tmp.name)
        self.assertEqual(r.returncode, 0, r.stderr)
        root = Path(self.tmp.name) / "zebra"
        self.assertTrue((root / ".git").exists())
        self.assertEqual(os.readlink(root / "CLAUDE.md"), "AGENTS.md")
        self.assertTrue((root / "bench" / "baseline.json").exists())
        self.assertNotIn("NAME", (root / "README.md").read_text())
        code, f = check(root)
        self.assertEqual(rules(f, "error"), set())
        self.assertEqual(code, 0)
        again = subprocess.run([sys.executable, str(FIUM), "new", "zebra"], capture_output=True, text=True, cwd=self.tmp.name)
        self.assertNotEqual(again.returncode, 0)
        self.assertIn("exists", again.stderr)


ROOT = FIUM.parent


class Docs(unittest.TestCase):
    def test_every_cited_rule_id_exists(self):
        ids = set(re.findall(r"\*\*([A-Z]\d+)\b", (ROOT / "RULES.md").read_text()))
        for doc in ("skills/fium/SKILL.md", "AGENTS.md"):
            cited = set(re.findall(r"\b([A-Z]\d+)\b", (ROOT / doc).read_text()))
            self.assertEqual(cited - ids, set(), doc)

    def test_help_describes_every_subcommand(self):
        out = subprocess.run([sys.executable, str(FIUM), "--help"], capture_output=True, text=True).stdout
        cmds = re.search(r"\{(.+?)\}", out).group(1).split(",")
        for c in cmds:
            self.assertRegex(out, rf"(?m)^\s+{c}\s+\S", c)


if __name__ == "__main__":
    unittest.main()
