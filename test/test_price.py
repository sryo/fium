import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

FIUM = Path(__file__).resolve().parent.parent / "fium"
os.environ["FIUM_HOME"] = tempfile.mkdtemp()


def run(*args, cwd=None):
    r = subprocess.run([sys.executable, str(FIUM), *args], capture_output=True, text=True, cwd=cwd)
    return r.returncode, r.stdout


def metric(samples, dir="lower", kind="time"):
    return {"dir": dir, "kind": kind, "samples": samples}


class Price(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, metrics, **extra):
        p = self.d / name
        p.write_text(json.dumps({"metrics": metrics, **extra}))
        return str(p)

    def compare(self, base, run_, *more):
        code, out = run("compare", "--json", base, run_, *more, cwd=self.d)
        return code, {m["metric"]: m for m in json.loads(out)}

    def test_compare_is_a_top_level_command(self):
        self.assertEqual(run("price", "compare", "a", "b")[0], 2)

    def test_same_within_noise(self):
        b = self.write("b.json", {"t": metric([100, 101, 99, 100, 102, 98, 100, 101])})
        r = self.write("r.json", {"t": metric([101, 100, 100, 99, 101, 99, 100, 102])})
        code, v = self.compare(b, r)
        self.assertEqual(v["t"]["verdict"], "same")
        self.assertEqual(code, 0)

    def test_clear_time_regression_is_worse(self):
        b = self.write("b.json", {"t": metric([100, 101, 99, 100, 102, 98, 100, 101])})
        r = self.write("r.json", {"t": metric([130, 131, 129, 130, 132, 128, 130, 131])})
        code, v = self.compare(b, r)
        self.assertEqual(v["t"]["verdict"], "worse")
        self.assertEqual(code, 1)

    def test_clear_improvement(self):
        b = self.write("b.json", {"t": metric([100] * 6)})
        r = self.write("r.json", {"t": metric([70] * 6)})
        _, v = self.compare(b, r)
        self.assertEqual(v["t"]["verdict"], "better")

    def test_noisy_borderline_is_inconclusive_and_blocks(self):
        b = self.write("b.json", {"t": metric([100, 140, 80, 120, 90, 110])})
        r = self.write("r.json", {"t": metric([115, 150, 95, 135, 100, 125])})
        code, v = self.compare(b, r)
        self.assertEqual(v["t"]["verdict"], "inconclusive")
        self.assertEqual(code, 3)

    def test_noisy_flag_makes_a_count_statistical(self):
        m = lambda xs: {"dir": "lower", "kind": "count", "noisy": True, "samples": xs}
        b = self.write("b.json", {"turns": m([58, 60, 55])})
        r = self.write("r.json", {"turns": m([59, 57, 61])})
        _, v = self.compare(b, r)
        self.assertNotEqual(v["turns"]["verdict"], "worse")

    def test_few_reps_judge_the_median_and_say_so(self):
        b = self.write("b.json", {"t": metric([100, 140, 80])})
        worse = self.write("w.json", {"t": metric([130, 150, 120])})
        same = self.write("s.json", {"t": metric([102, 139, 85])})
        code, v = self.compare(b, worse)
        self.assertEqual((v["t"]["verdict"], v["t"].get("low_n")), ("worse", True))
        self.assertEqual(code, 1)
        code, v = self.compare(b, same)
        self.assertEqual((v["t"]["verdict"], v["t"].get("low_n")), ("same", True))
        self.assertEqual(code, 0)

    def test_counts_any_increase_is_worse(self):
        b = self.write("b.json", {"calls": metric([4], kind="count")})
        r = self.write("r.json", {"calls": metric([5], kind="count")})
        _, v = self.compare(b, r)
        self.assertEqual(v["calls"]["verdict"], "worse")

    def test_quality_higher_is_better(self):
        b = self.write("b.json", {"q": metric([0.9], dir="higher", kind="quality")})
        r = self.write("r.json", {"q": metric([0.95], dir="higher", kind="quality")})
        _, v = self.compare(b, r)
        self.assertEqual(v["q"]["verdict"], "better")

    def test_noise_file_widens_rel(self):
        b = self.write("b.json", {"t": metric([100] * 6)})
        r = self.write("r.json", {"t": metric([115] * 6)})
        n = self.write("noise.json", {}, rel={"t": 0.2})
        _, v = self.compare(b, r, "--noise", n)
        self.assertEqual(v["t"]["verdict"], "same")

    def test_limit_is_never_crossed_even_if_priced(self):
        b = self.write("b.json", {"bytes": metric([900], kind="bytes")}, limits={"bytes": 1000})
        r = self.write("r.json", {"bytes": metric([1100], kind="bytes")})
        code, v = self.compare(b, r, "--price", "bytes")
        self.assertEqual(v["bytes"]["verdict"], "limit")
        self.assertEqual(code, 1)

    def test_priced_regression_passes(self):
        b = self.write("b.json", {"calls": metric([4], kind="count")})
        r = self.write("r.json", {"calls": metric([5], kind="count")})
        code, v = self.compare(b, r, "--price", "calls")
        self.assertEqual(v["calls"]["verdict"], "priced")
        self.assertEqual(code, 0)

    def test_goals_caps_set_how_firm_each_metric_is(self):
        subprocess.run(["git", "init", "-q", str(self.d)], check=True)
        (self.d / "GOALS.md").write_text("## How we know\nCaps: `q3 b1 t0 t.js*=2 big=3`\n")
        m = lambda v, k="bytes": metric([v], kind=k)
        b = self.write("b.json", {"dash": m(1000), "t.js": m(500), "big": m(10), "q": m(1, "quality"), "ms": m(5, "time")})
        r = self.write("r.json", {"dash": m(1080), "t.js": m(501), "big": m(11), "q": m(1, "quality"), "ms": m(9, "time")})
        code, v = self.compare(b, r, "--price", "t.js", "--price", "big")
        got = {k: v[k]["verdict"] for k in ["dash", "t.js", "big", "ms"]}
        self.assertEqual(got, {"dash": "grew", "t.js": "priced", "big": "worse", "ms": "grew"})
        self.assertEqual(code, 1)
        _, v = self.compare(b, self.write("r2.json", {"dash": m(1200), "t.js": m(500), "big": m(10), "q": m(1, "quality"), "ms": m(5, "time")}))
        self.assertEqual(v["dash"]["verdict"], "worse")

    def test_missing_metric_fails(self):
        b = self.write("b.json", {"a": metric([1], kind="count"), "b": metric([1], kind="count")})
        r = self.write("r.json", {"a": metric([1], kind="count")})
        code, v = self.compare(b, r)
        self.assertEqual(v["b"]["verdict"], "missing")
        self.assertEqual(code, 1)

    def test_paired_range_is_the_bootstrap_of_rep_by_rep_ratios(self):
        # The same numbers through Lede's compare.mjs give [1.0500, 1.1650]: one judge, whichever runs it.
        b = self.write("b.json", {"t": metric([10, 10.2, 9.9, 10.1, 10, 9.8, 10.3, 10])})
        r = self.write("r.json", {"t": metric([10.9, 11.4, 10.2, 11.8, 10.5, 11.1, 12, 10.7])})
        code, v = self.compare(b, r)
        self.assertEqual(v["t"]["range"], [1.05, 1.165])
        self.assertEqual(v["t"]["verdict"], "inconclusive")

    def test_a_time_that_stays_at_zero_is_same(self):
        b = self.write("b.json", {"t": metric([0, 0, 0, 0])})
        r = self.write("r.json", {"t": metric([0, 0, 0, 0])})
        code, out = run("compare", "--json", b, r, cwd=self.d)
        self.assertEqual(json.loads(out)[0]["verdict"], "same")
        self.assertEqual(code, 0)

    def test_a_time_that_falls_to_zero_is_better(self):
        b = self.write("b.json", {"t": metric([3, 2, 3, 2])})
        r = self.write("r.json", {"t": metric([0, 0, 0, 0])})
        self.assertEqual(self.compare(b, r)[1]["t"]["verdict"], "better")

    def test_a_gap_under_the_noise_files_abs_is_same(self):
        b = self.write("b.json", {"t": metric([0.020, 0.021, 0.021, 0.020, 0.020, 0.021])})
        r = self.write("r.json", {"t": metric([0.022, 0.023, 0.022, 0.023, 0.022, 0.023])})
        n = self.d / "noise.json"
        n.write_text(json.dumps({"rel": {"t": 0.1}, "abs": {"t": 0.05}}))
        self.assertNotEqual(self.compare(b, r)[1]["t"]["verdict"], "same")
        self.assertEqual(self.compare(b, r, "--noise", str(n))[1]["t"]["verdict"], "same")

    def test_a_limit_kind_is_judged_only_against_its_limit(self):
        b = self.write("b.json", {"h": metric([60000], dir="higher", kind="limit")}, limits={"h": 50000})
        self.assertEqual(self.compare(b, self.write("r.json", {"h": metric([55000], dir="higher", kind="limit")}))[1]["h"]["verdict"], "same")
        self.assertEqual(self.compare(b, self.write("r2.json", {"h": metric([40000], dir="higher", kind="limit")}))[1]["h"]["verdict"], "limit")


class Ledger(unittest.TestCase):
    def test_trailers_excuse_their_metric_since(self):
        with tempfile.TemporaryDirectory() as t:
            g = lambda *a: subprocess.run(["git", "-C", t, *a], capture_output=True, check=True)
            g("init", "-q"); g("config", "user.email", "a@b"); g("config", "user.name", "a")
            g("commit", "-q", "--allow-empty", "-m", "base"); g("tag", "base")
            g("commit", "-q", "--allow-empty", "-m", "x\n\nPrice: calls; 4 -> 5; buys: a; with semicolons; tried: b; owner: \"ok\", 2026-10-31")
            g("commit", "-q", "--allow-empty", "-m", "y\n\nBench-Accepted: bytes; 10 -> 12; buys: icons; owner: \"fine\", 2026-10-30")
            d = Path(t)
            m = lambda v, k: {"dir": "lower", "kind": k, "samples": [v]}
            (d / "b.json").write_text(json.dumps({"metrics": {"calls": m(4, "count"), "bytes": m(10, "bytes"), "q": m(1, "count")}}))
            (d / "r.json").write_text(json.dumps({"metrics": {"calls": m(5, "count"), "bytes": m(12, "bytes"), "q": m(2, "count")}}))
            code, out = run("compare", "--json", "--since", "base", "--repo", t, str(d / "b.json"), str(d / "r.json"))
            v = {r["metric"]: r["verdict"] for r in json.loads(out)}
            self.assertEqual(v, {"calls": "priced", "bytes": "priced", "q": "worse", "(commit)": "unstamped"})
            self.assertEqual(code, 1)
            # Growth past what the prices add up to is not covered by them.
            (d / "r2.json").write_text(json.dumps({"metrics": {"calls": m(6, "count"), "bytes": m(12, "bytes"), "q": m(1, "count")}}))
            code, out = run("compare", "--json", "--since", "base", str(d / "b.json"), str(d / "r2.json"))
            self.assertEqual({r["metric"]: r["verdict"] for r in json.loads(out)}["calls"], "worse")


class Stale(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        g = lambda *a: subprocess.run(["git", "-C", self.tmp.name, *a], capture_output=True, text=True, check=True).stdout.strip()
        g("init", "-q"); g("config", "user.email", "a@b"); g("config", "user.name", "a")
        g("commit", "-q", "--allow-empty", "-m", "old"); self.old = g("rev-parse", "HEAD")
        (self.d / "app.py").write_text("x"); g("add", "app.py"); g("commit", "-q", "-m", "new"); self.head = g("rev-parse", "HEAD")
        (self.d / "b.json").write_text(json.dumps({"metrics": {"calls": metric([4], kind="count")}}))

    def tearDown(self):
        self.tmp.cleanup()

    def compare(self, **stamp):
        (self.d / "r.json").write_text(json.dumps({"metrics": {"calls": metric([4], kind="count")}, **stamp}))
        code, out = run("compare", "--json", "b.json", "r.json", cwd=self.d)
        return code, {m["metric"]: m for m in json.loads(out)}

    def test_a_run_of_head_is_judged(self):
        code, v = self.compare(commit=self.head[:12], dirty=False)
        self.assertNotIn("(commit)", v)
        self.assertEqual(code, 0)

    def test_a_run_of_an_older_commit_is_stale_and_blocks(self):
        code, v = self.compare(commit=self.old)
        self.assertEqual(v["(commit)"]["verdict"], "stale")
        self.assertEqual(code, 1)

    def test_a_run_of_a_dirty_tree_is_stale(self):
        code, v = self.compare(commit=self.head, dirty=True)
        self.assertEqual(v["(commit)"]["verdict"], "stale")
        self.assertEqual(code, 1)

    def test_a_price_committed_after_its_run_keeps_it_fresh(self):
        g = lambda *a: subprocess.run(["git", "-C", self.tmp.name, *a], capture_output=True, check=True)
        (self.d / "bench").mkdir()
        (self.d / "bench" / "noise.json").write_text("{}")
        g("add", "bench"); g("commit", "-q", "-m", "p\n\nPrice: calls; 4 -> 5; buys: a; owner: \"ok\", 2026-10-31")
        code, v = self.compare(commit=self.head)
        self.assertEqual((v["(commit)"]["verdict"], code), ("carried", 0))
        (self.d / "code.py").write_text("x")
        g("add", "code.py"); g("commit", "-q", "-m", "q\n\nPrice: calls; 4 -> 5; buys: a; owner: \"ok\", 2026-10-31")
        self.assertEqual(self.compare(commit=self.head)[1]["(commit)"]["verdict"], "stale")

    def test_docs_carry_a_run_but_skill_docs_do_not(self):
        g = lambda *a: subprocess.run(["git", "-C", self.tmp.name, *a], capture_output=True, check=True)
        (self.d / "README.md").write_text("x"); (self.d / "tests").mkdir(); (self.d / "tests" / "a.py").write_text("x")
        g("add", "README.md", "tests"); g("commit", "-q", "-m", "docs")
        self.assertEqual(self.compare(commit=self.head)[1]["(commit)"]["verdict"], "carried")
        self.assertEqual(self.compare(commit=self.head, dirty=True)[1]["(commit)"]["verdict"], "stale")
        (self.d / "SKILL.md").write_text("x"); g("add", "SKILL.md"); g("commit", "-q", "-m", "skill")
        self.assertEqual(self.compare(commit=self.head)[1]["(commit)"]["verdict"], "stale")

    def test_a_bench_inert_file_extends_the_defaults(self):
        g = lambda *a: subprocess.run(["git", "-C", self.tmp.name, *a], capture_output=True, check=True)
        (self.d / "bench").mkdir(); (self.d / "bench" / "inert").write_text("# docs\nnotes/*\n")
        (self.d / "notes").mkdir(); (self.d / "notes" / "n.md").write_text("x")
        g("add", "bench", "notes"); g("commit", "-q", "-m", "n")
        self.assertEqual(self.compare(commit=self.head)[1]["(commit)"]["verdict"], "carried")
        (self.d / "README.md").write_text("x"); g("add", "README.md"); g("commit", "-q", "-m", "r")
        self.assertEqual(self.compare(commit=self.head)[1]["(commit)"]["verdict"], "carried")
        (self.d / "bench" / "inert").write_text("!defaults\nnotes/*\n"); g("add", "bench"); g("commit", "-q", "-m", "s")
        self.assertEqual(self.compare(commit=self.head)[1]["(commit)"]["verdict"], "stale")

    def test_a_judged_run_is_found_by_its_commit_from_any_cwd(self):
        (self.d / "b.json").write_text(json.dumps({"commit": self.old, "dirty": False, "metrics": {"calls": metric([4], kind="count")}}))
        self.compare(commit=self.head, dirty=False)
        with tempfile.TemporaryDirectory() as elsewhere:
            for rev in (self.old[:10], "HEAD~1"):
                code, out = run("compare", "--json", rev, str(self.d / "r.json"), "--repo", self.tmp.name, cwd=elsewhere)
                self.assertEqual((code, json.loads(out)[0]["verdict"]), (0, "same"), rev)
            code, _ = run("compare", "--json", "deadbeef", str(self.d / "r.json"), cwd=elsewhere)
            self.assertNotEqual(code, 0)
        self.assertTrue(list(Path(os.environ["FIUM_HOME"], "runs").glob(self.head + ".json")))

    def test_a_run_with_a_null_or_missing_commit_is_judged_and_not_kept(self):
        for stamp in ({"commit": None}, {}):
            code, v = self.compare(**stamp)
            self.assertEqual((code, v["(commit)"]["verdict"]), (0, "unstamped"), stamp)
        self.assertEqual(list(Path(os.environ["FIUM_HOME"]).glob("runs/None*")), [])

    def test_an_unstamped_run_is_flagged_but_does_not_block(self):
        code, v = self.compare()
        self.assertEqual(v["(commit)"]["verdict"], "unstamped")
        self.assertEqual(code, 0)


class Scope(unittest.TestCase):
    def test_scope_unions_tasks_and_fails_safe(self):
        with tempfile.TemporaryDirectory() as t:
            d = Path(t)
            g = lambda *a: subprocess.run(["git", "-C", t, *a], capture_output=True, check=True)
            g("init", "-q"); g("config", "user.email", "a@b"); g("config", "user.name", "a")
            g("commit", "-q", "--allow-empty", "-m", "base"); g("tag", "base")
            (d / "bench").mkdir()
            (d / "bench" / "affects.json").write_text(json.dumps({"rules": [
                {"files": ["lib/*.js"], "tasks": ["a", "b"]}, {"files": ["cap.py"], "tasks": ["c"]},
                {"files": ["bench/*"], "tasks": "none"}, {"files": ["SKILL.md"], "tasks": "*"}]}))
            (d / "lib").mkdir(); (d / "lib" / "x.js").write_text("x"); (d / "cap.py").write_text("x"); (d / "README.md").write_text("x")
            g("add", "-A"); g("commit", "-q", "-m", "c")
            sc = lambda: json.loads(run("scope", "--json", "base..HEAD", "--repo", t)[1])
            self.assertEqual(sc()["tasks"], ["a", "b", "c"])
            (d / "other.py").write_text("x"); g("add", "-A"); g("commit", "-q", "-m", "d")
            self.assertEqual(sc()["tasks"], "*")
            self.assertEqual(sc()["why"]["other.py"], "*")


if __name__ == "__main__":
    unittest.main()
