import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

FIUM = Path(__file__).resolve().parent.parent / "fium"
os.environ["FIUM_HOME"] = tempfile.mkdtemp()

GOALS = """# demo: goals

## Goals, in priority order
1. **Fast.**
2. **Works.**
3. **Looks right.**
4. **Small on disk.**
5. **Few tokens.**
6. **Small logs.**

## How we know
| Goal | Metric | Where | Run |
|---|---|---|---|
| 1 | answer time | `m.py` | `python3 m.py` |
| 2 | tests pass | `t.py` | `python3 t.py` |
| 3 | screens checked | by eye | by hand |
| 4 | data size | `du` | live: `cat d.txt` |
| 5 | tokens per task | eval | costly: `python3 e.py` |
| 6 | log lines | `l.py` | `python3 l.py \\| cat` |
| 7 | rules; size | `r.py` rules | `python3 r.py` |
| 7 | size | `r.py` size | `python3 r.py` |

Caps: `count=ask log*=ask+10% answer*=ask`
"""


# A bench that writes a run file and prints its path, like every project's bench.
R = """import json, sys
json.dump({"metrics": {n: {"dir": "lower", "kind": "count", "samples": [v]} for n, v in {"rules": 3, "size": 9, "extra": 1}.items()}}, open("run.json", "w"))
print("run.json")
"""


class Done(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.git("init", "-q", "-b", "main"); self.git("config", "user.email", "a@b"); self.git("config", "user.name", "a")
        self.write(**{"GOALS.md": GOALS, "m.py": "print(5)", "t.py": "pass", "e.py": "print(100)", "l.py": "print(100)", "r.py": R,
                      ".gitignore": "d.txt\n", "d.txt": "42\n"})
        self.git("add", "."); self.git("commit", "-q", "-m", "base")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *a):
        return subprocess.run(["git", "-C", str(self.d), *a], capture_output=True, text=True, check=True).stdout

    def write(self, **files):
        for name, text in files.items():
            (self.d / name).write_text(text)

    def done(self, *args):
        r = subprocess.run([sys.executable, str(FIUM), "done", *args], capture_output=True, text=True, cwd=self.d)
        return r.returncode, r.stdout

    def test_a_branch_is_measured_against_where_it_left_main_on_every_row(self):
        self.git("checkout", "-q", "-b", "feature")
        self.write(**{"m.py": "print(7)"}); self.git("commit", "-qam", "slower")
        code, out = self.done()
        self.assertIn("5 -> 7 (+2, +40%)", out, "each number of the project, from where the branch started to now")
        self.assertIn("screens checked", out, "a row nobody can run still shows, so no metric is lost")
        self.assertIn("by hand", out)
        self.assertIn("42 now", out, "a live row reads live state, here only")
        self.assertIn("not run", out, "a costly row says it wasn't run without --costly")
        self.assertNotIn("tokens per task:", out)
        self.assertEqual(code, 3, "something grew: the user decides whether it merges or gets simpler")
        self.assertIn("Not measured yet: tokens per task", out, "a costly row that didn't run keeps it from being done")
        self.assertEqual(self.git("worktree", "list").count("\n"), 1, "the base's worktree is gone")

    def test_each_cap_level_does_what_the_user_designed(self):
        self.done("--start")
        # Hard: not done until the same or better. Semi-hard: within its margin it passes, past it the user chooses.
        # Soft: no limit.
        caps = "Caps: `count=ask log*=ask+10% answer*=ask`"
        for line, out_m, out_l, code, says in [
            ("`count=ask log*=ask+10% answer*=hard`", "print(6)", "print(100)", 1, "same or better"),
            ("`count=ask log*=ask+10% answer*=ask`", "print(6)", "print(100)", 3, "the user lets it pass"),
            ("`count=ask log*=ask+10% answer*=ask+25%`", "print(6)", "print(100)", 0, "can merge"),
            ("`count=ask log*=ask+10% answer*=ask`", "print(5)", "print(105)", 0, "can merge"),
            ("`count=ask log*=ask+10% answer*=ask`", "print(5)", "print(120)", 3, "the user lets it pass"),
            ("`count=ask log*=free answer*=ask`", "print(5)", "print(150)", 0, "can merge"),
        ]:
            self.write(**{"GOALS.md": GOALS.replace(caps, "Caps: " + line), "m.py": out_m, "l.py": out_l})
            got, out = self.done("--costly")
            self.assertEqual(got, code, f"{line} m:{out_m} l:{out_l}\n{out}")
            self.assertIn(says, out, line)

    def test_old_digit_caps_still_hold_and_done_shows_them_in_words(self):
        self.write(**{"GOALS.md": GOALS.replace("Caps: `count=ask log*=ask+10% answer*=ask`", "Caps: `n2 log*=1 answer*=3`"),
                      "m.py": "print(6)"})
        code, out = self.done()
        self.assertEqual(code, 1, "answer*=3 is still hard\n" + out)
        self.assertIn("Caps: `count=ask loc=ask log*=ask+10% answer*=hard`", out, "the line to write instead, copy-ready")

    def test_a_number_that_should_rise_says_dropped_not_grew(self):
        score = R.replace('{n: {"dir": "lower", "kind": "count", "samples": [v]} for n, v in {"rules": 3, "size": 9, "extra": 1}.items()}',
                          '{"score": {"dir": "higher", "kind": "quality", "samples": [%s]}}')
        self.write(**{"r.py": score % 10, "GOALS.md": GOALS.replace("answer*=ask`", "answer*=ask quality=free`")})
        self.git("commit", "-qam", "score")
        self.write(**{"r.py": score % 9})
        out = self.done()[1]
        self.assertIn("dropped  score: 10 -> 9", out, "a higher-is-better number that fell didn't grow")

    def test_a_bench_metric_shows_once_under_the_row_that_names_it(self):
        self.write(**{"r.py": R.replace('"rules": 3, "size": 9, "extra": 1', '"rules": 4, "size": 10, "extra": 2')})
        code, out = self.done()
        self.assertEqual(out.count("rules: 3 -> 4"), 1)
        self.assertEqual(out.count("size: 9 -> 10"), 1, "named by two rows, it shows under the first")
        self.assertLess(out.index("  rules; size"), out.index("rules: 3 -> 4"))
        self.assertEqual(out.count("extra: 1 -> 2"), 1, "a metric no row names still shows, under the command's first row")
        self.assertEqual(out.count("`python3 r.py`: ok, as above"), 1, "the second row says it shares the first's run")
        self.assertEqual(next(l for l in out.splitlines() if "worse past" in l).count("rules"), 1, "each name once in the summary")

    def test_where_naming_a_metric_wins_over_a_row_that_only_mentions_the_word(self):
        self.write(**{"GOALS.md": GOALS.replace("| 7 | rules; size | `r.py` rules |", "| 7 | rules without an id | `r.py` unnamed |")
                      .replace("| 7 | size | `r.py` size |", "| 7 | rule count | `r.py` rules, size |"),
                      "r.py": R.replace('"rules": 3', '"rules": 4')})
        out = self.done()[1]
        self.assertLess(out.index("  rule count"), out.index("rules: 3 -> 4"))

    def test_a_noisy_number_that_got_better_without_certainty_asks_nothing(self):
        t = lambda xs: R.replace('{n: {"dir": "lower", "kind": "count", "samples": [v]} for n, v in {"rules": 3, "size": 9, "extra": 1}.items()}',
                                 '{"ms": {"dir": "lower", "kind": "time", "samples": %s}}' % xs)
        self.write(**{"r.py": t([100, 140, 80, 120, 90, 110])})
        self.git("commit", "-qam", "noisy base")
        self.write(**{"r.py": t([80, 133, 68, 120, 81, 97])})
        code, out = self.done()
        self.assertIn("inconclusive", out)
        self.assertEqual(code, 3, out)
        self.assertNotIn("worse past", out, "only the costly row keeps it open")

    def test_a_projects_measured_noise_judges_its_numbers_not_a_flat_ten_percent(self):
        t = lambda xs: R.replace('{n: {"dir": "lower", "kind": "count", "samples": [v]} for n, v in {"rules": 3, "size": 9, "extra": 1}.items()}',
                                 '{"ms": {"dir": "lower", "kind": "time", "samples": %s}}' % xs)
        self.write(**{"r.py": t([100, 100, 100])}); self.git("commit", "-qam", "base")
        self.write(**{"r.py": t([120, 120, 120])})
        self.assertIn("worse?  ms", self.done()[1], "with no noise file, 20% is past the default band")
        for where in ("bench", "tests/eval"):
            (self.d / where).mkdir(parents=True, exist_ok=True)
            (self.d / where / "noise.json").write_text(json.dumps({"rel": {"ms": 0.3}}))
            self.assertIn("same?  ms", self.done()[1], f"{where}/noise.json says this number moves 30% between identical runs")
            (self.d / where / "noise.json").unlink()

    def test_a_run_from_another_model_blocks(self):
        env = lambda m: R.replace('}, open(', '}, "env": {"model": "%s"}}, open(' % m).replace('.items()}}', '.items()}')
        self.write(**{"r.py": env("claude-opus-5-5")}); self.git("commit", "-qam", "opus")
        self.write(**{"r.py": env("claude-sonnet-5-5")})
        code, out = self.done()
        self.assertIn("not comparable", out)
        self.assertIn("ran on another model at the base", out, "the reason it's not done, in words")
        self.assertEqual(code, 1, "numbers from another model can't say whether this change can merge")

    def test_fewer_passing_tests_is_a_number_that_grew_the_wrong_way(self):
        self.write(**{"t.py": "print('Ran 12 tests in 0.1s')"}); self.git("commit", "-qam", "12 tests")
        self.write(**{"t.py": "print('Ran 10 tests in 0.1s')"})
        code, out = self.done()
        self.assertIn("tests passing: 12 -> 10 (-2, -16.7%)", out)
        self.assertEqual(code, 3)

    def test_a_row_sharing_a_command_says_so_and_a_live_row_shows_what_it_printed(self):
        self.write(**{"GOALS.md": GOALS.replace("| 5 | tokens per task |", "| 2 | tests again | t.py | `python3 t.py` |\n| 5 | tokens per task |")
                      .replace('live: `cat d.txt`', 'live: `python3 -c "print(\'up: none yet\')"`')})
        out = self.done()[1]
        self.assertIn("`python3 t.py`: ok, as above", out)
        self.assertIn("up: none yet", out)

    def test_a_live_row_with_no_number_leaves_the_change_open(self):
        # A live row is the project's only reading of what it measures; printing no number is not a measurement.
        self.done("--start")
        code, out = self.done("--costly")
        self.assertEqual(code, 0, out)
        for printed, why in [("print('up: none yet')", "printed no number"), ("raise SystemExit(1)", "fails")]:
            self.write(**{"GOALS.md": GOALS.replace('live: `cat d.txt`', f'live: `python3 -c "{printed}"`')})
            code, out = self.done("--costly")
            self.assertEqual(code, 3, out)
            self.assertIn(f"Couldn't measure: data size (live: {why})", out)

    def test_a_live_row_is_held_to_the_before_read_when_the_plan_was_frozen(self):
        # Live state has no base commit to read it at, so its before is read once, when the plan is frozen.
        code, out = self.done("--costly")
        self.assertEqual(code, 3, out)
        self.assertIn("Couldn't measure: data size (live: no before)", out)
        self.assertIn("fium done --start", out, "says how to get a before")
        code, out = self.done("--start")
        self.assertEqual(code, 0, out)
        self.assertIn("data size: 42", out, "shows what it read")
        code, out = self.done("--start")
        self.assertEqual(code, 1, "a before is read once; reading it again would move it past the change")
        code, out = self.done("--costly")
        self.assertEqual(code, 0, out)
        self.assertIn("same  data size: 42", out)
        self.write(**{"d.txt": "50\n"})
        code, out = self.done("--costly")
        self.assertIn("data size: 42 -> 50 (+8, +19%)", out, "now held to the before, like any row")
        self.assertEqual(code, 3, out)

    def test_a_live_row_that_writes_a_run_file_shows_its_numbers_not_no_output(self):
        # A row's Metric cell is prose ("rules; size"), not a metric's name; what it read is the run file's numbers.
        self.write(**{"GOALS.md": GOALS.replace('| 4 | data size | `du` | live: `cat d.txt` |', '| 4 | rules; size | `r.py` | live: `python3 r.py` |')})
        code, out = self.done("--start")
        self.assertEqual(code, 0, out)
        self.assertNotIn("no output", out)
        self.assertIn("rules: 3", out)
        self.assertIn("size: 9", out)
        (Path(os.environ["FIUM_HOME"]) / "runs").exists() and [f.unlink() for f in (Path(os.environ["FIUM_HOME"]) / "runs").rglob("*.live.json")]
        out = self.done("--costly")[1]
        self.assertNotIn("no output", out, "a live row with no before still shows what it read")
        self.assertIn("size: 9", out)

    def test_a_live_before_that_read_no_number_measures_nothing(self):
        self.write(**{"d.txt": "none yet\n"})
        self.done("--start")
        self.write(**{"d.txt": "42\n"})
        code, out = self.done("--costly")
        self.assertEqual(code, 3, out)
        self.assertIn("data size (live: no before)", out)

    def test_a_cached_base_is_read_again_by_todays_rules_and_a_new_metric_shows(self):
        self.done()
        self.write(**{"r.py": R.replace('"extra": 1}', '"extra": 1, "fresh": 4}')})
        out = self.done()[1]
        self.assertIn("new  fresh: 4", out)
        self.assertIn("same  rules: 3", out, "the base came from the cache and still reads")

    def test_a_number_takes_its_cap_from_the_kind_its_row_names(self):
        self.write(**{"GOALS.md": GOALS.replace("| 6 | log lines |", "| 6 | log bytes |").replace("Caps: `count=ask log*=ask+10% answer*=ask`", "Caps: `count=ask bytes=hard`"),
                      "l.py": "print(101)"})
        code, out = self.done()
        self.assertIn("log bytes: 100 -> 101", out)
        self.assertEqual(code, 1, "bytes are hard here, counts aren't")

    def test_a_command_that_failed_at_the_base_leaves_the_change_open(self):
        self.write(**{"t.py": "raise SystemExit(1)"}); self.git("commit", "-qam", "broken base")
        code, out = self.done("--costly")
        self.assertIn("Couldn't measure: tests pass (fails before and after)", out)
        self.write(**{"GOALS.md": GOALS.replace("| 5 | tokens per task |", "| 2 | tests again | t.py | `python3 t.py` |\n| 5 | tokens per task |")})
        self.assertIn("tests again (fails before and after)", self.done("--costly")[1], "every row that runs it is named")
        self.assertEqual(code, 3, "failing before doesn't make it fine now")
        self.write(**{"t.py": "pass"})
        code, out = self.done("--costly")
        self.assertIn("ok now, failed at the base", out, "the failed base wasn't cached as if it were fine, nor skipped")
        self.assertIn("Couldn't measure: tests pass (failed at the base)", out)
        self.assertEqual(code, 3)

    def test_a_costly_rows_base_is_measured_fresh_beside_now_never_cached(self):
        self.write(**{"e.py": "import os; print(os.environ.get('WORLD', '1'))"}); self.git("commit", "-qam", "world")
        os.environ["WORLD"] = "1"; self.done("--costly")
        os.environ["WORLD"] = "5"
        try:
            out = self.done("--costly")[1]
        finally:
            del os.environ["WORLD"]
        self.assertIn("same  tokens per task: 5", out, "the world changed between runs: both sides see the new one")

    def test_several_runners_counts_add_up(self):
        self.write(**{"t.py": "print('Ran 33 tests in 0.1s'); print('ℹ pass 512')"})
        self.assertIn("tests passing: 545", self.done()[1])

    def test_pytests_summary_counts_tests_once_not_as_the_rows_number(self):
        self.write(**{"t.py": "print('123 passed in 1.1s')"})
        out = self.done()[1]
        self.assertIn("tests passing: 123", out)
        self.assertNotIn("tests pass: 123", out)

    def test_a_pattern_in_where_claims_the_metrics_it_matches(self):
        self.write(**{"GOALS.md": GOALS.replace("| 7 | size | `r.py` size |", "| 7 | per-op size | `r.py` `si<op>` |")})
        out = self.done()[1]
        self.assertLess(out.index("  per-op size"), out.index("same  size: 9"))

    def test_the_base_is_measured_beside_the_repo_so_sibling_checkouts_are_found(self):
        (self.d.parent / (self.d.name + "-sib")).mkdir()
        try:
            self.write(**{"GOALS.md": GOALS + "| 8 | sibling | x | `test -d ../%s-sib && echo 1 \\|\\| echo 0` |\n" % self.d.name})
            self.git("commit", "-qam", "sib row")
            self.write(**{"m.py": "print(4)"})
            out = self.done()[1]
            self.assertIn("same  sibling: 1", out)
            self.assertFalse([p for p in self.d.parent.iterdir() if p.name.startswith(".fium-done-")], "no worktree left beside it")
        finally:
            (self.d.parent / (self.d.name + "-sib")).rmdir()

    def test_an_unchanged_number_a_row_or_a_cap_names_still_shows_among_many(self):
        many = '{**{f"op{i}": 1 for i in range(9)}, "beacon bytes": 50, "rules": 3}'
        self.write(**{"r.py": R.replace('{"rules": 3, "size": 9, "extra": 1}', many),
                      "GOALS.md": GOALS.replace("Caps: `count=ask log*=ask+10% answer*=ask`", "Caps: `count=ask beacon*=ask`")})
        self.git("commit", "-qam", "many")
        self.write(**{"m.py": "print(4)"})
        out = self.done()[1]
        self.assertIn("same  beacon bytes: 50", out, "a Caps override names it")
        self.assertIn("same  rules: 3", out, "its row names it")
        self.assertIn("9 same", out, "the rest collapse")
        self.write(**{"GOALS.md": GOALS.replace("Caps: `count=ask log*=ask+10% answer*=ask`", "Caps: `count=ask beacon*=ask`").replace("| 7 | rules; size | `r.py` rules |", "| 7 | rules; size | `r.py` rules, `op<n>` |")})
        self.assertIn("9 same", self.done()[1], "a pattern places metrics but doesn't keep them on show")

    def test_a_command_dropped_from_the_table_after_the_base_was_cached_is_ignored(self):
        self.done()
        self.write(**{"GOALS.md": GOALS.replace("`python3 m.py`", "`python3 m.py && true`")})
        code, out = self.done()
        self.assertNotIn("Traceback", out)
        self.assertIn("answer time", out)

    def test_rows_show_under_their_goals_name_not_its_number(self):
        out = self.done()[1]
        self.assertIn("\nFast\n  answer time", out)
        self.assertIn("\nWorks\n  tests pass", out)

    def test_a_row_of_a_few_numbers_shows_them_even_when_unchanged(self):
        out = self.done()[1]
        self.assertIn("same  answer time: 5", out)

    def test_uncommitted_work_on_main_is_measured_against_head(self):
        self.done("--start")
        self.write(**{"m.py": "print(4)"})
        code, out = self.done("--costly")
        self.assertIn("5 -> 4 (-1, -20%)", out)
        self.assertEqual(code, 0, "nothing grew, nothing broke, everything ran: it can merge")

    def test_a_command_that_now_fails_blocks(self):
        self.write(**{"t.py": "raise SystemExit(1)"})
        code, out = self.done()
        self.assertIn("python3 t.py", out)
        self.assertIn("fails", out)
        self.assertEqual(code, 1)

    def test_costly_rows_run_only_when_asked_and_are_compared(self):
        self.done("--start")
        self.write(**{"e.py": "print(80)"})
        code, out = self.done("--costly")
        self.assertIn("100 -> 80 (-20, -20%)", out)
        self.assertEqual(code, 0)


# 25 lines of code a change adds: a path a user can take that, by itself, no number shows.
APP = "".join(f"x{i} = {i}\n" for i in range(24)) + "print(1)\n"
ROW = "| 2 | picks delivered | `app.py` | {run} |\n| 5 | tokens per task |"


class Adds(unittest.TestCase):
    # K4: a change that adds code needs a better number, or a new row that runs what it adds the way the user does.
    setUp, tearDown, git, write, done = Done.setUp, Done.tearDown, Done.git, Done.write, Done.done

    def feature(self, goals=None, **files):
        self.done("--start")
        self.git("checkout", "-q", "-b", "feature")
        self.write(**{"app.py": APP, **files, **({"GOALS.md": goals} if goals else {})})
        self.git("add", "."); self.git("commit", "-qm", "adds")
        return self.done("--costly")

    def test_k4_code_that_no_number_shows_leaves_the_change_open(self):
        code, out = self.feature(**{"t.py": "print('Ran 12 tests in 0.1s')"})
        self.assertEqual(code, 3, out)
        self.assertIn("adds 25 lines of code no number shows", out)
        self.assertIn("the way the user does", out, "says what row would show it")
        self.assertIn("each fallback", out)
        self.assertIn("what the screen shows after", out)

    def test_k4_untracked_code_counts(self):
        self.git("checkout", "-q", "-b", "feature")
        self.write(**{"app.py": APP})
        code, out = self.done("--costly")
        self.assertIn("adds 25 lines of code", out, "a new file not yet added is still code the change adds")

    def test_k4_a_small_change_isnt_asked(self):
        code, out = self.feature(**{"app.py": "print(1)\n"})
        self.assertNotIn("no number shows", out)

    def test_k4_tests_benches_and_docs_arent_code_it_adds(self):
        self.git("checkout", "-q", "-b", "feature")
        for d in ("test", "bench"):
            (self.d / d).mkdir()
            self.write(**{f"{d}/x.py": APP})
        self.write(**{"notes.md": APP})
        self.assertNotIn("no number shows", self.done("--costly")[1])

    def test_k4_a_better_number_shows_it(self):
        code, out = self.feature(**{"m.py": "print(4)"})
        self.assertEqual(code, 0, out)

    def test_k4_a_new_row_shows_it_and_reads_new_not_couldnt_measure(self):
        code, out = self.feature(GOALS.replace("| 5 | tokens per task |", ROW.format(run="`python3 app.py`")))
        self.assertEqual(code, 0, out)
        self.assertIn("new  picks delivered: 1", out)
        self.assertNotIn("Couldn't measure", out, "a row the change adds has no base to fail at")

    def test_k4_a_new_live_row_reads_new_not_no_before(self):
        code, out = self.feature(GOALS.replace("| 5 | tokens per task |", ROW.format(run="live: `python3 app.py`")))
        self.assertEqual(code, 0, out)
        self.assertIn("new  picks delivered: 1", out)
        self.assertNotIn("no before", out)

    def test_k4_a_new_row_that_reads_no_number_measures_nothing(self):
        code, out = self.feature(GOALS.replace("| 5 | tokens per task |", ROW.format(run="`python3 -c \"print('ok')\"`")))
        self.assertEqual(code, 3, out)
        self.assertIn("Couldn't measure: picks delivered (new row printed no number)", out)

    def test_k4_a_new_row_that_fails_blocks(self):
        code, out = self.feature(GOALS.replace("| 5 | tokens per task |", ROW.format(run="`python3 -c \"raise SystemExit(1)\"`")))
        self.assertEqual(code, 1, out)

    def test_k4_a_dry_new_row_is_named(self):
        code, out = self.feature(GOALS.replace("| 5 | tokens per task |", ROW.format(run="`python3 app.py --dry`")))
        self.assertIn("picks delivered: its row says dry", out)
        self.assertIn("doesn't run it the way the user does", out)

    def test_k4_a_row_dropped_since_the_base_is_a_cut_to_ask_about(self):
        code, out = self.feature(GOALS.replace("| 6 | log lines | `l.py` | `python3 l.py \\| cat` |\n", ""), **{"app.py": "print(1)\n"})
        self.assertEqual(code, 3, out)
        self.assertIn("Dropped from How we know: log lines", out)

    def test_k4_a_reworded_command_is_not_a_new_row(self):
        self.write(**{"GOALS.md": GOALS.replace("`python3 m.py`", "`python3 m.py && true`")})
        out = self.done()[1]
        self.assertIn("same  answer time: 5", out, "the row was at the base, so it's still held to it")


class Docs(unittest.TestCase):
    # K4/W3: the real run is K4's row, recorded and run again; no doc still asks for an unrecorded one.
    def test_k4_w3_the_real_run_is_a_row(self):
        root = Path(__file__).resolve().parent.parent
        rules, skill = (root / "RULES.md").read_text(), (root / "SKILL.md").read_text()
        self.assertFalse("one real run" in rules + skill, "the real run is K4's row now")
        k4 = next(l for l in rules.splitlines() if l.startswith("- **K4"))
        for words in ("the way the user does", "each fallback", "what they see"):
            self.assertIn(words, k4)


if __name__ == "__main__":
    unittest.main()
