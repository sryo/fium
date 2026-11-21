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
        self.assertEqual(set(m), {"rules", "untested_checks", "unnamed_rules", "read_bytes", "loc", "check_ms", "compare_ms", "check_all_ms"})
        for name, v in m.items():
            self.assertIn(v["dir"], ("lower", "higher"), name)
            self.assertTrue(v["samples"], name)
        self.assertEqual(len(m["check_ms"]["samples"]), 2)
        self.assertEqual(run["limits"], {"untested_checks": 0, "unnamed_rules": 0})

    def test_a_run_with_no_path_lands_outside_the_repo_under_fium_home(self):
        r = subprocess.run([sys.executable, str(BENCH), "--reps", "1"], capture_output=True, text=True, cwd=ROOT)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(Path(r.stdout.strip()).parent, Path(os.environ["FIUM_HOME"], "runs", "fium"))

    def test_paired_runs_time_the_baseline_commit_and_head_alternately(self):
        head = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        with tempfile.TemporaryDirectory() as t:
            r = subprocess.run([sys.executable, str(BENCH), "--reps", "3", "--paired", "HEAD", str(Path(t) / "run.json")],
                               capture_output=True, text=True, cwd=ROOT)
            self.assertEqual(r.returncode, 0, r.stderr)
            base_path, run_path = r.stdout.split()
            base, run = json.loads(Path(base_path).read_text()), json.loads(Path(run_path).read_text())
        self.assertEqual((base["commit"], base["dirty"]), (head, False))
        for name in ("check_ms", "compare_ms", "check_all_ms"):
            self.assertEqual(len(base["metrics"][name]["samples"]), 3)
            self.assertEqual(len(run["metrics"][name]["samples"]), 3)
        sys.path.insert(0, str(ROOT / "bench"))
        from run import code, exact, reader
        for name, m in exact(reader(head), code(head)).items():
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


def entry(role, *blocks):
    return json.dumps({"type": role, "message": {"role": role, "content": list(blocks)}})


def said(s):
    return entry("user", {"type": "text", "text": s})


def bash(i, cmd, out):
    return [entry("assistant", {"type": "tool_use", "id": i, "name": "Bash", "input": {"command": cmd}}),
            entry("user", {"type": "tool_result", "tool_use_id": i, "content": out})]


WORSE = "loc got worse past its margin. Simplify it, or the user lets it pass."


class Hook(unittest.TestCase):
    # The turn-end hook replayed on sessions whose blocks were labelled by hand: what it sent back that it shouldn't
    # have, and what it let through that it should have sent back.
    def session(self, t, name, lines):
        f = Path(t, name + ".jsonl")
        f.write_text("\n".join(lines) + "\n")
        return str(f)

    def run_hook(self, t, labels):
        Path(t, "labels.json").write_text(json.dumps(labels))
        out = Path(t, "run.json")
        r = subprocess.run([sys.executable, str(ROOT / "bench" / "hook.py"), "--labels", str(Path(t, "labels.json")), str(out)],
                           capture_output=True, text=True, cwd=ROOT)
        return r, (json.loads(out.read_text()) if out.exists() else None)

    def test_counts_wrong_and_missed_blocks_against_the_labels(self):
        with tempfile.TemporaryDirectory() as t:
            # Pushed after a not-done verdict, then the user spoke (line 5), then the session ended clean.
            landed = self.session(t, "landed", [said("build it"), *bash("d", "fium done | grep loc", WORSE),
                                                *bash("p", "git push -q", ""), said("thanks"), *bash("q", "ls", "")])
            # The same push on the last turn: the hook runs when the session ends too (-1).
            last = self.session(t, "last", [said("build it"), *bash("d", "fium done", WORSE), *bash("p", "git push", "")])
            clean = self.session(t, "clean", [said("push it"), *bash("p", "git push", "")])
            r, run = self.run_hook(t, {landed: [5], last: [-1], clean: []})
            self.assertEqual(r.returncode, 0, r.stderr)
            m = run["metrics"]
            self.assertEqual((m["wrong_blocks"]["samples"], m["missed_blocks"]["samples"]), ([0], [0]))
            self.assertEqual(run["limits"], {"wrong_blocks": 0, "missed_blocks": 0})
            self.assertEqual(m["hook_ms"]["kind"], "time")
            r, run = self.run_hook(t, {landed: [], last: [], clean: [1]})
            m = run["metrics"]
            self.assertEqual((m["wrong_blocks"]["samples"], m["missed_blocks"]["samples"]), ([2], [1]))
            self.assertIn("last.jsonl", r.stderr, "each wrong or missed block is named")

    def test_missing_labels_or_a_missing_session_fails_instead_of_counting_zero(self):
        with tempfile.TemporaryDirectory() as t:
            r = subprocess.run([sys.executable, str(ROOT / "bench" / "hook.py"), "--labels", str(Path(t, "none.json"))],
                               capture_output=True, text=True, cwd=ROOT)
            self.assertNotEqual(r.returncode, 0)
            r, run = self.run_hook(t, {str(Path(t, "gone.jsonl")): []})
            self.assertNotEqual(r.returncode, 0)
            self.assertIn("gone.jsonl", r.stderr)
            self.assertIsNone(run)


if __name__ == "__main__":
    unittest.main()
