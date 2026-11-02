import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

FIUM = Path(__file__).resolve().parent.parent / "fium"


class Repo(unittest.TestCase):
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

    def fium(self, *args, **env):
        r = subprocess.run([sys.executable, str(FIUM), "try", *args], capture_output=True, text=True, cwd=self.d, env={**self.env, **env})
        return r.returncode, r.stdout + r.stderr


class Try(Repo):
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


GOALS = """# demo: goals

## Goals, in priority order
1. **Small.**

## How we know
| Goal | Metric | Where | Run |
|---|---|---|---|
| 1 | loc, calls, ms | `r.py` | `python3 r.py` |
"""

# A bench that counts tool.py's lines and reads the calls and times an eval would have measured from files.
BENCH = """import json
m = lambda kind, s: {"dir": "lower", "kind": kind, "samples": s}
json.dump({"metrics": {"loc": m("loc", [len(open("tool.py").read().splitlines())]),
                       "calls": m("count", [int(open("calls.txt").read())]),
                       "ms": m("time", json.loads(open("ms.txt").read()))}}, open("run.json", "w"))
print("run.json")
"""


class Keep(Repo):
    def setUp(self):
        super().setUp()
        self.commit("bench", **{"GOALS.md": GOALS, "r.py": BENCH, "tool.py": "a\nb\nc\n", "calls.txt": "10", "ms.txt": "[100, 100, 100]",
                                "README.md": "why\nhow\nmore\n", ".gitignore": "run.json\n"})
        self.git("checkout", "-q", "-b", "loop")
        self.fium("baseline", "--record", "keep")

    def attempt(self, idea, *more, **files):
        self.commit(idea, **files)
        code, out = self.fium(idea, *more)
        return code, out.strip().splitlines()[-1], out

    def test_a_cut_that_leaves_every_other_number_the_same_is_kept(self):
        code, last, out = self.attempt("drop a line", **{"tool.py": "a\nb\n"})
        self.assertEqual((code, last), (0, "keep"), out)
        self.assertIn("loc: 3 -> 2", out, "the reason is the numbers that moved")
        self.assertEqual(json.loads(self.log()[-1])["status"], "keep", "the attempt is logged")

    def test_an_addition_that_improves_nothing_is_dropped(self):
        code, last, out = self.attempt("add a line", **{"tool.py": "a\nb\nc\nd\n", "calls.txt": "10"})
        self.assertEqual((code, last), (1, "discard"), out)
        code, last, out = self.attempt("rename", **{"SKILL.md": "renamed\n"})
        self.assertEqual(last, "discard", "an addition must make its target better, not just leave things the same")

    def test_an_addition_is_kept_when_its_target_gets_better_and_nothing_else_worse(self):
        code, last, out = self.attempt("batch calls", "--target", "calls", **{"tool.py": "a\nb\nc\n# batch\n", "calls.txt": "7"})
        self.assertEqual(last, "discard", "it added a line, and lines are worse")
        code, last, out = self.attempt("batch calls in place", "--target", "calls", **{"tool.py": "a\nb\nc\n", "calls.txt": "7"})
        self.assertEqual((code, last), (0, "keep"), out)

    def test_cutting_what_nothing_measures_is_parked_not_kept(self):
        code, last, out = self.attempt("trim the readme", **{"README.md": "why\nhow\n"})
        self.assertEqual(last, "park", "nothing measured read it, so nothing says the cut is safe")
        code, last, out = self.attempt("shorter words", **{"README.md": "y\n"})
        self.assertEqual(last, "park", "a shorter line is a cut too: bytes, not lines")

    def test_a_command_that_now_fails_is_a_crash(self):
        code, last, out = self.attempt("break it", **{"calls.txt": "ten"})
        self.assertEqual((code, last), (1, "crash"), out)

    def test_a_noisy_number_too_close_to_call_that_got_worse_is_retested(self):
        self.commit("noisy", **{"ms.txt": "[100, 140, 80, 120, 90, 110]"}); self.fium("noisy base", "--record", "keep")
        code, last, out = self.attempt("cut and maybe slower", **{"tool.py": "a\nb\n", "ms.txt": "[108, 160, 60, 135, 95, 118]"})
        self.assertEqual(last, "retest", out + "\nan inconclusive number that moved the wrong way needs more reps before a keep")

    def test_small_rises_that_pass_one_at_a_time_cant_add_up(self):
        code, last, out = self.attempt("cut a", "--target", "calls", **{"calls.txt": "9", "ms.txt": "[108, 108, 108]"})
        self.assertEqual(last, "keep", "8% is within the band")
        code, last, out = self.attempt("cut b", "--target", "calls", **{"calls.txt": "8", "ms.txt": "[116, 116, 116]"})
        self.assertEqual(last, "discard", "16% since the branch left main is past the band")
        self.assertIn("since main", out)

    def test_an_attempt_that_changes_the_judge_is_refused_and_not_logged(self):
        n = len(self.log())
        code, last, out = self.attempt("lenient", **{"tests/eval/run.py": "lenient\n", "tool.py": "a\n"})
        self.assertEqual(code, 1)
        self.assertIn("changes the judge", out)
        self.assertEqual(len(self.log()), n)

    def log(self):
        return (Path(self.tmp.name) / "home" / "runs" / "demo" / "tries.jsonl").read_text().splitlines()


# An agent eval: what it spends now varies run to run (TOKENS; the base's run spends 100), and each run is counted.
EVAL = """import os
open(os.environ["COUNT"], "a").write("x")
print(os.environ["TOKENS"] if os.path.realpath(os.getcwd()) == os.environ["HERE"] else "100")
"""


class Confirm(Repo):
    def setUp(self):
        super().setUp()
        self.count = Path(self.tmp.name) / "count"
        self.commit("bench", **{"GOALS.md": GOALS + "| 1 | tokens per task | eval | costly: `python3 e.py` |\n", "r.py": BENCH,
                                "e.py": EVAL, "tool.py": "a\nb\nc\n", "calls.txt": "10", "ms.txt": "[100, 100, 100]"})
        self.git("checkout", "-q", "-b", "loop")
        self.fium("baseline", "--record", "keep")

    def live(self, *args, tokens="100"):
        code, out = self.fium(*args, "--costly", COUNT=str(self.count), TOKENS=tokens, HERE=os.path.realpath(self.d))
        return code, out.strip().splitlines()[-1], out

    def test_a_live_keep_holds_only_if_fresh_reps_agree(self):
        self.commit("cut", **{"tool.py": "a\nb\n"})
        code, last, out = self.live("cut")
        self.assertEqual((code, last), (0, "confirm"), "a keep that rested on an agent eval is measured again before it counts")
        code, last, out = self.live("--confirm", tokens="150")
        self.assertEqual((code, last), (1, "discard"), out)
        self.assertIn("didn't hold on fresh reps", out, "the logged numbers come from the fresh reps, not the lucky run")

    def test_a_confirmed_keeps_runs_are_the_next_attempts_base(self):
        self.commit("cut", **{"tool.py": "a\nb\n"}); self.live("cut")
        self.assertEqual(self.live("--confirm")[1], "keep")
        self.commit("cut more", **{"tool.py": "a\n"})
        before = len(self.count.read_text())
        self.assertEqual(self.live("cut more")[1], "confirm")
        self.assertEqual(len(self.count.read_text()) - before, 1, "the eval ran here only: its base is the confirmed keep's runs")


if __name__ == "__main__":
    unittest.main()
