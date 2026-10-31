import json, subprocess, sys, tempfile, unittest
from pathlib import Path
from test_check import README, make

FIUM = Path(__file__).resolve().parent.parent / "fium"


def git(root, *a):
    return subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True, check=True).stdout


class Survey(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.docs = Path(self.tmp.name)
        for i, name in enumerate(("aa", "bb", "cc")):
            root = self.docs / name
            root.mkdir()
            readme = README.replace("demo", name) + "\n## Troubleshooting\nRestart it.\n"
            agents = f"# {name}\n" + ("\n## Bench\nrun it\n" if i < 2 else "")
            make(root, **{"README.md": readme, "AGENTS.md": agents, "LICENSE": None if i == 2 else "x\n"})
            git(root, "init", "-q"); git(root, "config", "user.email", "a@b"); git(root, "config", "user.name", "a")
            git(root, "add", "-A")
            git(root, "commit", "-q", "-m", "move CLAUDE.md to a symlink (F2)" if i == 0 else "init")

    def tearDown(self):
        self.tmp.cleanup()

    def survey(self, *more):
        r = subprocess.run([sys.executable, str(FIUM), "survey", "--json", str(self.docs), *more], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def test_counts_failures_per_rule_and_passing_repos(self):
        s = self.survey()
        self.assertEqual(s["repos"], 3)
        self.assertEqual(s["passing"], 2)
        self.assertEqual(s["failures"], {"F5": 1})

    def test_sections_most_repos_add_to_a_template_are_drift(self):
        s = self.survey()
        self.assertEqual(s["drift"], {"README.md": {"troubleshooting": 3}})
        self.assertEqual(self.survey("--min", "2")["drift"]["AGENTS.md"], {"bench": 2})

    def test_cited_and_never_cited_rules(self):
        s = self.survey()
        self.assertEqual(s["cited"], {"F2": 1})
        self.assertIn("K4", s["uncited"])
        self.assertNotIn("F2", s["uncited"])

    def test_never_writes_to_a_repo(self):
        self.survey()
        for name in ("aa", "bb", "cc"):
            self.assertEqual(git(self.docs / name, "status", "--porcelain"), "")


if __name__ == "__main__":
    unittest.main()
