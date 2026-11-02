import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

FIUM = Path(__file__).resolve().parent.parent / "fium"


class Try(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name) / "demo"
        self.d.mkdir()
        self.env = {**os.environ, "FIUM_HOME": str(Path(self.tmp.name) / "home")}
        self.git("init", "-q", "-b", "main"); self.git("config", "user.email", "a@b"); self.git("config", "user.name", "a")
        self.commit("base", **{"SKILL.md": "a\n", "tool.py": "x = 1\n", "tests/eval/run.py": "judge\n"})

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *a):
        return subprocess.run(["git", "-C", str(self.d), *a], capture_output=True, text=True, check=True).stdout.strip()

    def commit(self, msg, **files):
        for name, text in files.items():
            (self.d / name).parent.mkdir(parents=True, exist_ok=True)
            (self.d / name).write_text(text)
        self.git("add", "-A"); self.git("commit", "-q", "-m", msg)

    def fium(self, *args):
        r = subprocess.run([sys.executable, str(FIUM), "try", *args], capture_output=True, text=True, cwd=self.d, env=self.env)
        return r.returncode, r.stdout + r.stderr

    def test_every_attempt_is_listed_with_what_was_tried_and_why_it_was_kept_or_dropped(self):
        self.commit("shorter skill", **{"SKILL.md": "b\n"})
        self.fium("shorter skill", "--record", "keep", "--reason", "read bytes 900 -> 700, nothing worse")
        self.commit("cache the lookup", **{"tool.py": "x = 2\n"})
        self.fium("cache the lookup", "--record", "discard", "--reason", "tokens 40k -> 52k")
        code, out = self.fium()
        self.assertEqual(code, 0, out)
        for said in ("keep", "shorter skill", "read bytes 900 -> 700", "discard", "cache the lookup", "tokens 40k -> 52k", "1 of 2 kept"):
            self.assertIn(said, out, "the log says what was tried and why it stayed or went")
        rows = [json.loads(l) for l in (Path(self.tmp.name) / "home" / "runs" / "demo" / "tries.jsonl").read_text().splitlines()]
        self.assertEqual([r["files"] for r in rows], [["SKILL.md"], ["tool.py"]], "each attempt remembers what it touched")

    def test_five_attempts_in_a_row_with_no_keep_say_stop_or_change_approach(self):
        self.fium("baseline", "--record", "keep")
        for i in range(4):
            self.fium(f"idea {i}", "--record", "discard", "--reason", "worse")
        self.assertNotIn("stop or change approach", self.fium()[1])
        self.fium("idea 4", "--record", "crash", "--reason", "tests fail")
        self.assertIn("5 in a row with no keep: stop or change approach", self.fium()[1])

    def test_ideas_dropped_before_that_touched_the_same_files_are_shown_before_trying_again(self):
        self.fium("baseline", "--record", "keep")
        self.commit("trim the skill", **{"SKILL.md": "c\n"})
        self.fium("trim the skill", "--record", "discard", "--reason", "turns 2 -> 4: the agent asked for the cut rule")
        self.git("reset", "-q", "--hard", "HEAD~1")
        (self.d / "SKILL.md").write_text("d\n")
        out = self.fium()[1]
        self.assertIn("Dropped before, touching what you changed", out)
        self.assertIn("turns 2 -> 4: the agent asked for the cut rule", out, "read why it went before trying it again")

    def test_an_attempt_may_add_to_the_judge_but_never_change_it(self):
        self.fium("baseline", "--record", "keep")
        (self.d / "tests/eval/scorers").mkdir(parents=True)
        (self.d / "tests/eval/scorers/new.py").write_text("more checked\n")
        self.git("add", "-A")
        self.assertNotIn("judge", self.fium()[1], "a new scorer checks more; adding one is fine")
        (self.d / "tests/eval/run.py").write_text("lenient judge\n")
        code, out = self.fium()
        self.assertEqual(code, 1, "an attempt that changes how it's judged can't be judged")
        self.assertIn("changes the judge: tests/eval/run.py", out)
        (self.d / "bench").mkdir()
        (self.d / "bench/judge").write_text("!defaults\nnothing/*\n")
        self.assertNotIn("changes the judge", self.fium()[1], "bench/judge replaces the defaults when it says !defaults")


if __name__ == "__main__":
    unittest.main()
