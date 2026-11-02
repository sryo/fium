import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path
from test_check import README, make

FIUM = Path(__file__).resolve().parent.parent / "fium"


def git(root, *a):
    return subprocess.run(["git", "-C", str(root), *a], capture_output=True, text=True, check=True).stdout


def commit(root, name, text, msg):
    (root / name).write_text(text)
    git(root, "add", name)
    git(root, "commit", "-q", "-m", msg)


class Status(unittest.TestCase):
    # aa: base main; feat merged; wip one ahead, in a worktree whose test passes; bad one ahead, test fails.
    # bb: main checkout on next, the branch the user develops on; old is merged into next.
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.docs = Path(self.tmp.name) / "docs"
        self.home = Path(self.tmp.name) / "home"
        self.aa, self.bb = self.docs / "aa", self.docs / "bb"
        for root in (self.aa, self.bb):
            root.mkdir(parents=True)
            git(root, "init", "-q", "-b", "main")
            git(root, "config", "user.email", "a@b"); git(root, "config", "user.name", "a")
            commit(root, "AGENTS.md", "# x\n\n## Test\n```bash\ntest -f ok\n```\n", "init")
        git(self.aa, "branch", "feat")
        git(self.aa, "branch", "wip"); git(self.aa, "branch", "bad")
        self.wt = Path(self.tmp.name) / "aa-wip"
        git(self.aa, "worktree", "add", "-q", str(self.wt), "wip")
        commit(self.wt, "ok", "", "wip work")
        self.bad = Path(self.tmp.name) / "aa-bad"
        git(self.aa, "worktree", "add", "-q", str(self.bad), "bad")
        commit(self.bad, "other", "", "bad work")
        (self.aa / "scratch").write_text("")
        git(self.bb, "switch", "-q", "-c", "next")
        commit(self.bb, "next.txt", "calls fium price compare\n", "dev work")
        git(self.bb, "branch", "old")

    def tearDown(self):
        self.tmp.cleanup()

    def run_fium(self, *a):
        env = dict(os.environ, FIUM_HOME=str(self.home))
        r = subprocess.run([sys.executable, str(FIUM), *a], capture_output=True, text=True, env=env)
        return r

    def status(self, *more):
        r = self.run_fium("status", "--json", str(self.docs), *more)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout)

    def campaign(self, repos):
        (self.home / "campaigns").mkdir(parents=True, exist_ok=True)
        (self.home / "campaigns" / "c1.json").write_text(json.dumps({"repos": repos}))

    def test_base_is_the_branch_the_main_checkout_is_on(self):
        s = self.status()
        self.assertEqual(s["aa"]["base"], "main")
        self.assertEqual(s["bb"]["base"], "next")

    def test_branches_merged_or_ahead_with_their_worktrees(self):
        s = self.status()
        br = s["aa"]["branches"]
        self.assertEqual(br["feat"]["merged"], True)
        self.assertEqual(br["wip"], {"merged": False, "ahead": 1, "worktree": str(self.wt.resolve())})
        self.assertEqual(s["bb"]["branches"]["old"]["merged"], True)
        self.assertNotIn("next", s["bb"]["branches"])

    def test_counts_dirty_files(self):
        s = self.status()
        self.assertEqual(s["aa"]["dirty"], 1)
        self.assertEqual(s["bb"]["dirty"], 0)

    def test_campaign_reruns_each_branch_test_command_at_its_tip(self):
        self.campaign({"aa": ["wip", "bad"]})
        s = self.status("--campaign", "c1")
        wip, bad = s["aa"]["branches"]["wip"]["test"], s["aa"]["branches"]["bad"]["test"]
        self.assertEqual(wip["exit"], 0)
        self.assertEqual(wip["commit"], git(self.wt, "rev-parse", "HEAD").strip())
        self.assertNotEqual(bad["exit"], 0)

    def test_campaign_prints_cleanup_only_for_its_merged_branches(self):
        self.campaign({"aa": ["feat", "wip"], "bb": ["old"]})
        r = self.run_fium("status", str(self.docs), "--campaign", "c1")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(f"git -C {self.aa.resolve()} branch -d feat", r.stdout)
        self.assertIn(f"git -C {self.bb.resolve()} branch -d old", r.stdout)
        self.assertNotIn("branch -d wip", r.stdout)
        self.assertNotIn("branch -d bad", r.stdout)

    def test_a_merged_branch_in_a_worktree_gets_its_worktree_removed_first(self):
        git(self.aa, "merge", "-q", "--ff-only", "wip")
        self.campaign({"aa": ["wip"]})
        out = self.run_fium("status", str(self.docs), "--campaign", "c1").stdout
        rm, delete = out.index(f"worktree remove {self.wt.resolve()}"), out.index("branch -d wip")
        self.assertLess(rm, delete)

    def test_never_writes_to_a_repo(self):
        before = [git(r, "status", "--porcelain") + git(r, "branch") for r in (self.aa, self.bb)]
        self.campaign({"aa": ["feat", "wip", "bad"], "bb": ["old"]})
        self.status("--campaign", "c1")
        after = [git(r, "status", "--porcelain") + git(r, "branch") for r in (self.aa, self.bb)]
        self.assertEqual(before, after)

    def test_unknown_campaign_names_where_it_looked(self):
        r = self.run_fium("status", str(self.docs), "--campaign", "nope")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn(str(self.home / "campaigns" / "nope.json"), r.stderr)

    def test_a_symlinked_repo_is_listed_once(self):
        (self.docs / "zz").symlink_to(self.aa)
        commit(self.aa, "a.txt", "only in aa\n", "a")
        r = self.run_fium("grep", "only in aa", str(self.docs))
        self.assertEqual(r.stdout.count("a.txt"), 1)
        self.assertEqual(sorted(self.status()), ["aa", "bb"])

    def test_grep_searches_each_repo_at_its_base_not_its_worktrees(self):
        commit(self.wt, "w.txt", "price compare\n", "only on wip")
        r = self.run_fium("grep", "price compare", str(self.docs))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("bb next:next.txt:1:calls fium price compare", r.stdout)
        self.assertNotIn("w.txt", r.stdout)


class Survey(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.docs = Path(self.tmp.name)
        for i, name in enumerate(("aa", "bb", "cc")):
            root = self.docs / name
            root.mkdir()
            readme = README.replace("demo", name) + "\n## Troubleshooting\nRestart it.\n"
            agents = f"# {name}\n\n## Test\nmake test\nA change is done when `fium done` says so.\n" + ("\n## Bench\nrun it\n" if i < 2 else "")
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
