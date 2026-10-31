import os, subprocess, sys, tempfile, unittest, json
from pathlib import Path

HOUSE = Path(__file__).resolve().parent.parent / "house"

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


def make(root, **over):
    files = {"AGENTS.md": "# demo\n", "README.md": README, "GOALS.md": GOALS, "LICENSE": "x\n"}
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


def check(root):
    r = subprocess.run([sys.executable, str(HOUSE), "check", "--json", str(root)], capture_output=True, text=True)
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
        r = subprocess.run([sys.executable, str(HOUSE), "check", "--json", "--all", self.tmp.name], capture_output=True, text=True)
        out = json.loads(r.stdout)
        self.assertEqual(list(out), ["demo"])

    def test_every_goal_needs_a_row(self):
        make(self.root, **{"GOALS.md": GOALS.replace("1. **Fast.**", "1. **Fast.**\n2. **Small.**")})
        _, f = check(self.root)
        self.assertTrue(any(x["rule"] == "G2" and "goal 2" in x["msg"] for x in f))

    def test_use_section_required(self):
        make(self.root, **{"README.md": README.split("## Use")[0]})
        _, f = check(self.root)
        self.assertIn("R3", rules(f, "error"))

    def test_slash_title_allowed(self):
        make(self.root, **{"README.md": README.replace("# demo", "# /demo")})
        _, f = check(self.root)
        self.assertNotIn("R1", rules(f))

    def test_build_and_internals_sections_warn(self):
        make(self.root, **{"README.md": README + "\n## Development\nnpm run build\n\n## Architecture\nx\n"})
        code, f = check(self.root)
        self.assertEqual(code, 0)
        self.assertIn("R5", rules(f, "warn"))


if __name__ == "__main__":
    unittest.main()
