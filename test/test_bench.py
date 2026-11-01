import json, os, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BENCH = ROOT / "bench" / "run.py"
# fium compare keeps runs under FIUM_HOME; the suite never writes to the real ~/.fium.
os.environ["FIUM_HOME"] = tempfile.mkdtemp()


class Bench(unittest.TestCase):
    def test_writes_a_stamped_run_in_the_price_format(self):
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "run.json"
            r = subprocess.run([sys.executable, str(BENCH), "--reps", "2", str(out)], capture_output=True, text=True, cwd=ROOT)
            self.assertEqual(r.returncode, 0, r.stderr)
            run = json.loads(out.read_text())
        head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        self.assertEqual(run["commit"], head)
        self.assertIsInstance(run["dirty"], bool)
        m = run["metrics"]
        self.assertEqual(set(m), {"rules", "untested_checks", "unnamed_rules", "read_bytes", "loc", "check_ms", "compare_ms"})
        for name, v in m.items():
            self.assertIn(v["dir"], ("lower", "higher"), name)
            self.assertTrue(v["samples"], name)
        self.assertEqual(len(m["check_ms"]["samples"]), 2)
        self.assertEqual(run["limits"], {"untested_checks": 0, "unnamed_rules": 0})

    def test_paired_runs_time_the_baseline_commit_and_head_alternately(self):
        head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        with tempfile.TemporaryDirectory() as t:
            r = subprocess.run([sys.executable, str(BENCH), "--reps", "3", "--paired", "HEAD", str(Path(t) / "run.json")],
                               capture_output=True, text=True, cwd=ROOT)
            self.assertEqual(r.returncode, 0, r.stderr)
            base_path, run_path = r.stdout.split()
            base, run = json.loads(Path(base_path).read_text()), json.loads(Path(run_path).read_text())
        self.assertEqual((base["commit"], base["dirty"]), (head, False))
        for name in ("check_ms", "compare_ms"):
            self.assertEqual(len(base["metrics"][name]["samples"]), 3)
            self.assertEqual(len(run["metrics"][name]["samples"]), 3)
        sys.path.insert(0, str(ROOT / "bench"))
        from run import exact, reader
        for name, m in exact(reader(head)).items():
            self.assertEqual(base["metrics"][name], m, name)

    def test_a_command_that_fails_is_not_a_timing(self):
        sys.path.insert(0, str(ROOT / "bench"))
        from run import wall_ms
        self.assertGreaterEqual(wall_ms([sys.executable, "-c", ""], ROOT), 0)
        with self.assertRaisesRegex(SystemExit, "exited 3"):
            wall_ms([sys.executable, "-c", "raise SystemExit(3)"], ROOT)

    def test_paired_with_a_rev_that_is_not_a_commit_fails_and_says_why(self):
        r = subprocess.run([sys.executable, str(BENCH), "--paired", "bench/runs/x.json"], capture_output=True, text=True, cwd=ROOT)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("is not a commit", r.stderr)

    def test_a_checked_rule_without_a_test_is_counted(self):
        sys.path.insert(0, str(ROOT / "bench"))
        from run import untested_checks
        rules = "- **F1 ✓** a.\n- **F2 ✓** b.\n- **L1** c.\n"
        self.assertEqual(untested_checks(rules, 'assertEqual(f["rule"], "F1")'), 1)

    def test_a_rule_without_an_id_is_counted(self):
        sys.path.insert(0, str(ROOT / "bench"))
        from run import unnamed_rules
        rules = "## Files (F)\n- **F1 ✓** a.\n- no id here.\n  - a sub-point is fine.\n"
        self.assertEqual(unnamed_rules(rules), 1)


if __name__ == "__main__":
    unittest.main()
