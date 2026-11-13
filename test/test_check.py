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
| Goal | Metric | Where | Run |
|---|---|---|---|
| 1 | p50 per call | `bench/baseline.json` | `make bench` |

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


AGENTS = "# demo\n\n## Test\n```bash\nmake test\n```\nA change is done when `fium done` says so.\n"

def make(root, **over):
    files = {"AGENTS.md": AGENTS, "README.md": README, "GOALS.md": GOALS, "LICENSE": "x\n", ".gitignore": ".DS_Store\n"}
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
        make(self.root, **{"GOALS.md": None, "LICENSE": None, "README.md": None, ".gitignore": None})
        code, f = check(self.root)
        self.assertEqual(code, 1)
        self.assertEqual({x["file"] for x in f if x["rule"] == "F1"}, {"GOALS.md", "LICENSE", "README.md", ".gitignore"})

    def test_gitignore_keeps_finder_files_out(self):
        make(self.root, **{".gitignore": "node_modules\n"})
        code, f = check(self.root)
        self.assertEqual(code, 1)
        hit = [x for x in f if x["rule"] == "F1"][0]
        self.assertEqual(hit["file"], ".gitignore")
        self.assertIn(".DS_Store", hit["fix"])

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

    def test_metric_row_says_how_done_runs_it(self):
        make(self.root)
        for goals, why in ((GOALS.replace(" Run |", "").replace("|---|---|---|---|", "|---|---|---|").replace(" `make bench` |", ""), "no Run column"),
                           (GOALS.replace("`make bench`", ""), "an empty Run cell")):
            (self.root / "GOALS.md").write_text(goals)
            _, f = check(self.root)
            self.assertTrue(any(x["rule"] == "G2" and x["level"] == "warning" and "Run" in x["msg"] for x in f),
                            f"fium done can't measure a row with {why}")
        for run in ("live: `du -sk data`", "by hand"):
            (self.root / "GOALS.md").write_text(GOALS.replace("`make bench`", run))
            self.assertNotIn("G2", rules(check(self.root)[1]), run)

    def test_agents_says_to_judge_a_change_with_fium_done(self):
        make(self.root)
        plain = AGENTS.replace("A change is done when `fium done` says so.\n", "")
        (self.root / "AGENTS.md").write_text(plain)
        f = check(self.root)[1]
        self.assertTrue(any(x["rule"] == "K3" and "fium done" in x["msg"] for x in f),
                        "a project with goals tells its agents how to know a change is done")
        (self.root / "AGENTS.md").write_text(plain + "\n## Bench\nRun `fium compare base.json run.json --since main` with `bench.mjs --house x`.\n")
        f = check(self.root)[1]
        self.assertTrue(any(x["rule"] == "K3" and "--since" in x["msg"] for x in f), "the old way is named so it can go")
        (self.root / "AGENTS.md").write_text(plain + "\n## Bench\nA change is done when `fium done` says so.\n")
        self.assertNotIn("K3", rules(check(self.root)[1]))

    def test_readme_opener_names_what_it_does(self):
        make(self.root, **{"README.md": "# Demo\n\n`demo` is a thing.\n\n## Install\nx\n"})
        _, f = check(self.root)
        self.assertIn("R1", rules(f), "the opener starts with the plain name")
        (self.root / "README.md").write_text(README.replace("# demo", "# Demo"))
        self.assertNotIn("R1", rules(check(self.root)[1]), "a title in any case is just a title")

    def test_readme_without_install(self):
        make(self.root, **{"README.md": "# demo\n\ndemo does X.\n"})
        _, f = check(self.root)
        self.assertIn("R2", rules(f, "error"))

    def test_a_fix_that_touches_no_test_warns(self):
        make(self.root)
        g = lambda *a: subprocess.run(["git", "-C", str(self.root), *a], capture_output=True, check=True)
        g("init", "-q"); g("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "start", "--allow-empty")
        def commit(msg, **files):
            for name, body in files.items():
                (self.root / name).parent.mkdir(parents=True, exist_ok=True)
                (self.root / name).write_text(body)
            g("add", "-A"); g("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", msg)
        commit("Fix the parser on empty input", **{"parse.py": "x = 1\n"})
        commit("fix: tested", **{"parse.py": "x = 2\n", "test/test_parse.py": "pass\n"})
        commit("Fix a typo in the README", **{"README.md": README + "x\n"})
        commit("Add a prefix option", **{"parse.py": "x = 3\n"})
        _, f = check(self.root)
        hits = [x for x in f if x["rule"] == "W2"]
        self.assertEqual([h["level"] for h in hits], ["warn"], hits)
        self.assertIn("Fix the parser on empty input", hits[0]["msg"])
        self.assertIn("test that fails on the bug", hits[0]["fix"])

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
        hits = [x for x in json.loads(r.stdout)["demo"] if x["rule"] == "F4"]
        self.assertEqual(len(hits), 1)
        self.assertIn("over budget", hits[0]["msg"])
        (self.root / "bench" / "checks").write_text("true\n")
        r = subprocess.run([sys.executable, str(FIUM), "check", "--json", "--all", self.tmp.name], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_every_goal_needs_a_row(self):
        make(self.root, **{"GOALS.md": GOALS.replace("1. **Fast.**", "1. **Fast.**\n2. **Small.**")})
        _, f = check(self.root)
        self.assertTrue(any(x["rule"] == "G2" and "goal 2" in x["msg"] for x in f))

    def test_a_missing_use_section_warns(self):
        make(self.root, **{"README.md": README.split("## Use")[0]})
        _, f = check(self.root)
        self.assertIn("R2", rules(f, "warn"))
        self.assertNotIn("R2", rules(f, "error"))

    def test_a_logo_block_may_open_the_readme(self):
        logo = '<p align="center">\n  <picture>\n    <source srcset="d.svg">\n    <img src="l.svg" alt="demo">\n  </picture>\n</p>\n\n'
        make(self.root)
        for readme in (logo + README, logo + README.split("\n", 2)[2], "![demo](logo.png)\n\n" + README):
            (self.root / "README.md").write_text(readme)
            _, f = check(self.root)
            self.assertNotIn("R1", rules(f), readme)
        (self.root / "README.md").write_text(logo + "Some tagline.\n\n## Install\nx\n\n## Use\ny\n")
        self.assertNotIn("R1", rules(check(self.root)[1]))
        (self.root / "README.md").write_text(logo.replace('alt="demo"', 'alt="Logo"') + "Some tagline.\n\n## Install\nx\n\n## Use\ny\n")
        self.assertIn("R1", rules(check(self.root)[1]))

    def test_build_and_internals_sections_warn(self):
        make(self.root, **{"README.md": README + "\n## Development\nnpm run build\n\n## Architecture\nx\n"})
        code, f = check(self.root)
        self.assertEqual(code, 0)
        self.assertIn("R3", rules(f, "warn"))

    def test_agents_md_has_a_test_section(self):
        make(self.root, **{"AGENTS.md": "# demo\n\n## Build\nmake\n"})
        code, f = check(self.root)
        self.assertEqual(code, 1)
        self.assertIn("F3", rules(f, "error"))

    def test_new_project_passes_check(self):
        r = subprocess.run([sys.executable, str(FIUM), "new", "zebra"], capture_output=True, text=True, cwd=self.tmp.name)
        self.assertEqual(r.returncode, 0, r.stderr)
        root = Path(self.tmp.name) / "zebra"
        self.assertTrue((root / ".git").exists())
        self.assertEqual(os.readlink(root / "CLAUDE.md"), "AGENTS.md")
        self.assertTrue((root / "bench" / "baseline.json").exists())
        self.assertEqual((root / "LICENSE").read_text(), (FIUM.parent / "LICENSE").read_text())
        self.assertNotIn("NAME", (root / "README.md").read_text())
        self.assertFalse((root / "DESIGN.md").exists())
        self.assertIn(".DS_Store", (root / ".gitignore").read_text())
        code, f = check(root)
        self.assertEqual(rules(f, "error"), set())
        self.assertEqual(code, 0)
        again = subprocess.run([sys.executable, str(FIUM), "new", "zebra"], capture_output=True, text=True, cwd=self.tmp.name)
        self.assertNotEqual(again.returncode, 0)
        self.assertIn("exists", again.stderr)

    def test_new_project_leaves_the_caps_to_the_owner(self):
        r = subprocess.run([sys.executable, str(FIUM), "new", "zebra"], capture_output=True, text=True, cwd=self.tmp.name)
        self.assertRegex(r.stdout, r"Caps:.*ask", "the template's Caps line is a default only the user may change (K6)")

    def test_new_project_tells_the_agent_the_codebase_is_its_own_to_shape(self):
        subprocess.run([sys.executable, str(FIUM), "new", "zebra"], capture_output=True, text=True, cwd=self.tmp.name)
        agents = (Path(self.tmp.name) / "zebra" / "AGENTS.md").read_text()
        self.assertIn("This codebase is yours to shape", agents, "without it an agent bolts onto the structure like a guest")
        self.assertIn("named as the next change", agents, "what's outside the change stays out of it (W3)")


ROOT = FIUM.parent


class Docs(unittest.TestCase):
    def test_every_cited_rule_id_exists(self):
        ids = set(re.findall(r"\*\*([A-Z]\d+)\b", (ROOT / "RULES.md").read_text()))
        for doc in ("SKILL.md", "across.md", "loop.md", "AGENTS.md", "README.md", "templates/GOALS.md", "templates/AGENTS.md"):
            cited = set(re.findall(r"\b([A-Z]\d+)\b", (ROOT / doc).read_text()))
            self.assertEqual(cited - ids, set(), doc)

    def test_a_project_asked_for_is_done_only_when_every_readme_promise_is_built(self):
        # A promise the plan left out went unbuilt while fium done passed; done covers the README, not only the plan.
        rules = (ROOT / "RULES.md").read_text()
        w1, w3 = (re.search(rf"^- \*\*{w}\*\* .*$", rules, re.M)[0] for w in ("W1", "W3"))
        self.assertIn("an R for each README or GOALS promise asked for", w1)
        self.assertIn("every promise in README and GOALS", w3)
        new = (ROOT / "SKILL.md").read_text().split("## Start a new project")[1].split("## ")[0]
        self.assertIn("Build every promise README and GOALS make", new)

    def test_the_agent_answers_for_the_project_and_lands_what_the_user_called_done(self):
        # Projects made before the template said so had no such line; an agent asked "merge all" merged its own two
        # commits, then asked about the push and about a stale branch nobody else was going to settle.
        rules = (ROOT / "RULES.md").read_text()
        w5 = re.search(r"^- \*\*W5\*\* .*$", rules, re.M)[0]
        self.assertIn("The project is yours while you work in it", w5)
        self.assertIn("landing it is yours too", w5, "the user's done (K3) is the go-ahead for the commit, merge and push")
        self.assertIn("every branch", w5)
        self.assertIn("merge it or discard it", w5, "a stale branch is settled, not reported")
        self.assertIn("without asking", w5)
        self.assertIn("Only the user decides", w5, "what stays theirs is listed, so owning isn't deciding done or deleting their data")
        self.assertIn("(W5)", (ROOT / "SKILL.md").read_text())

    def test_across_keeps_the_manager_out_of_its_sessions_work(self):
        sessions = (ROOT / "across.md").read_text().split("## 3. One session per repo")[1].split("\n## ")[0]
        self.assertIn("cheaper model than yours", sessions)
        self.assertIn("gets a follow-up", sessions)
        self.assertIn("Never do its work yourself", sessions)

    def test_check_reports_exactly_the_ticked_rules(self):
        # A finding cites a rule that still exists, and a rule marked as checked has a check behind it.
        rules_md = (ROOT / "RULES.md").read_text()
        ticked = set(re.findall(r"^- \*\*([A-Z]\d+) ✓\*\*", rules_md, re.M))
        emitted = set(re.findall(r'finding\("([A-Z]\d+)"', (ROOT / "check.py").read_text()))
        emitted |= set(re.findall(r'\("([A-Z]\d+)", "[\w.]+"\)', (ROOT / "check.py").read_text()))
        self.assertEqual(emitted, ticked)

    def test_layout_names_every_top_level_entry_and_nothing_else(self):
        # Each file says what it's for in one place, and a moved or new one can't go unlisted.
        layout = re.search(r"^## Layout\n(.*?)(?=^## |\Z)", (ROOT / "AGENTS.md").read_text(), re.M | re.S)
        self.assertTrue(layout, "AGENTS.md has no ## Layout")
        listed = set(re.findall(r"^- `([^`/]+)/?`", layout.group(1), re.M))
        tracked = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True).stdout.split()
        top = {f.split("/")[0] for f in tracked if (ROOT / f).exists()} - {"CLAUDE.md"}
        self.assertEqual(top - listed, set(), "tracked but not in ## Layout")
        self.assertEqual(listed - top, set(), "in ## Layout but not tracked")

    def test_help_describes_every_subcommand(self):
        out = subprocess.run([sys.executable, str(FIUM), "--help"], capture_output=True, text=True).stdout
        cmds = re.search(r"\{(.+?)\}", out).group(1).split(",")
        for c in cmds:
            self.assertRegex(out, rf"(?m)^\s+{c}\s+\S", c)

    def test_skill_docs_call_fium_the_way_install_puts_it(self):
        install = re.search(r"^## Install\n(.*?)(?=^## )", (ROOT / "README.md").read_text(), re.M | re.S).group(1)
        self.assertIn("https://raw.githubusercontent.com/sryo/fium/main/install.sh | bash", install, "Install is install.sh's one-liner")
        self.assertIn('link "$FIUM_DIR/fium" "$bin_dir/fium"', (ROOT / "install.sh").read_text(),
                      "install.sh puts fium on PATH, so bare `fium` runs anywhere")
        for doc in ("README.md", "SKILL.md", "loop.md", "across.md"):
            calls = re.sub(r"(?m)^ln -sfn .*\n", "", (ROOT / doc).read_text())
            self.assertNotIn("fium/fium", calls, f"{doc} calls fium by path; one spelling, the one Install sets up")

    def test_readme_names_learning_and_the_skill_names_what_the_user_sets(self):
        use = re.search(r"^## Use\n(.*)", (ROOT / "README.md").read_text(), re.M | re.S).group(1)
        self.assertIn("learn", use, "learning from past sessions is a flow you'd ask for")
        self.assertIn("Caps:", (ROOT / "SKILL.md").read_text(), "only the user writes how firm each number is (K6), so the agent must ask")

    def test_skill_names_every_bench_file_and_learn_subcommand(self):
        skill = (ROOT / "SKILL.md").read_text()
        files = set(re.findall(r"`bench/([\w.-]+)`", (ROOT / "RULES.md").read_text())) | {"learn.json"}
        for f in files:
            self.assertRegex(skill, rf"`[^`]*\b{re.escape(f)}`", f"bench/{f} is set up per project, so the skill lists it")
        sys.path.insert(0, str(ROOT)); import learn
        subs = next(x for x in learn.parser()._actions if x.choices).choices
        for s in subs:
            self.assertRegex(skill, rf"`[^`]*\b{s}`", f"fium learn {s}")


if __name__ == "__main__":
    unittest.main()
