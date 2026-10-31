import json, subprocess, sys, tempfile, unittest
from pathlib import Path

FIUM = Path(__file__).resolve().parent.parent / "fium"


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
        code, out = run("price", "compare", "--json", base, run_, *more, cwd=self.d)
        return code, {m["metric"]: m for m in json.loads(out)}

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
        code, out = run("price", "compare", "--json", b, r, cwd=self.d)
        self.assertEqual(json.loads(out)[0]["verdict"], "same")
        self.assertEqual(code, 0)

    def test_a_time_that_falls_to_zero_is_better(self):
        b = self.write("b.json", {"t": metric([3, 2, 3, 2])})
        r = self.write("r.json", {"t": metric([0, 0, 0, 0])})
        self.assertEqual(self.compare(b, r)[1]["t"]["verdict"], "better")

    def test_a_gap_under_the_noise_files_abs_is_same(self):
        b = self.write("b.json", {"t": metric([0.020, 0.021, 0.021, 0.020])})
        r = self.write("r.json", {"t": metric([0.022, 0.023, 0.022, 0.023])})
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
            code, out = run("price", "compare", "--json", "--since", "base", str(d / "b.json"), str(d / "r.json"))
            v = {r["metric"]: r["verdict"] for r in json.loads(out)}
            self.assertEqual(v, {"calls": "priced", "bytes": "priced", "q": "worse"})
            self.assertEqual(code, 1)
            # Growth past what the prices add up to is not covered by them.
            (d / "r2.json").write_text(json.dumps({"metrics": {"calls": m(6, "count"), "bytes": m(12, "bytes"), "q": m(1, "count")}}))
            code, out = run("price", "compare", "--json", "--since", "base", str(d / "b.json"), str(d / "r2.json"))
            self.assertEqual({r["metric"]: r["verdict"] for r in json.loads(out)}["calls"], "worse")



if __name__ == "__main__":
    unittest.main()
