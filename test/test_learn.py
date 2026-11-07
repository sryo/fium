import json, os, re, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

FIUM = Path(__file__).resolve().parent.parent / "fium"

HINTS = """HINTS = [
    (r'unloaded font', 'load it first: await figma.loadFontAsync(node.fontName)'),
    (r'FILL can only be set on children of auto-layout', 'appendChild to an auto-layout frame first'),
    (r'HUG can only be set on auto-layout', 'set layoutMode first'),
    (r'must be in the same page as the parent', 'nodes on two pages: move one first'),
]
"""
MJS = """const HIDDEN_HINT = "The tab is hidden (document.visibilityState is hidden): bring it to the front";
const UNDEFINED_HINT = "figma is undefined in this tab: open a design file first";
"""


def use(i, ts, name, inp):
    return {"type": "assistant", "timestamp": ts, "sessionId": "S1",
            "message": {"role": "assistant", "content": [{"type": "tool_use", "id": i, "name": name, "input": inp}]}}


def result(i, ts, text, err=False):
    return {"type": "user", "timestamp": ts, "sessionId": "S1",
            "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": i, "is_error": err, "content": text}]}}


def human(ts, text):
    return {"type": "user", "timestamp": ts, "sessionId": "S1", "origin": {"kind": "human"}, "message": {"role": "user", "content": text}}


RUN = "python3 helper.py --lib -e \"await __fx.text({parent, chars: 'Hi'})\""
TRANSCRIPT = [
    human("2026-10-30T10:00:00Z", "build the login screen"),
    use("t1", "2026-10-30T10:00:05Z", "Bash", {"command": RUN}),
    result("t1", "2026-10-30T10:00:06Z", 'Exit code 1\n✗ Evaluation error: in set_characters: Cannot write to node with unloaded font "Inter Regular"', True),
    use("t2", "2026-10-30T10:00:10Z", "Bash", {"command": RUN.replace("Hi", "Hey")}),
    result("t2", "2026-10-30T10:00:11Z", 'Exit code 1\n✗ Evaluation error: in set_characters: Cannot write to node with unloaded font "Inter Bold"', True),
    use("t3", "2026-10-30T10:00:15Z", "Bash", {"command": RUN.replace("Hi", "Hello")}),
    result("t3", "2026-10-30T10:01:40Z", '{"id":"1:2"}'),
    use("t4", "2026-10-30T10:01:45Z", "Read", {"file_path": "/x/lib.js"}),
    result("t4", "2026-10-30T10:01:46Z", "x" * 30000),
    use("t5", "2026-10-30T10:01:50Z", "Agent", {"prompt": "go"}),
    result("t5", "2026-10-30T10:09:50Z", "done"),
    human("2026-10-30T10:10:00Z", "no, don't rebuild the header, edit it in place"),
    human("2026-10-30T10:11:00Z", "[Request interrupted by user]"),
    human("2026-10-30T10:12:00Z", "<system-reminder>not a person</system-reminder>"),
]
FONT_SIG = "in set_characters: cannot write to node with unloaded font <s>"


class Learn(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.home = os.path.join(self.tmp, "fium")
        self.repo = os.path.join(self.tmp, "demo")
        self.config({"projects": ["demo", "perch"], "hints": ["helper.py", "batch.py"], "hint_consts": ["helper.mjs"],
                     "gates": [["python3", "-m", "unittest"], ["python3", "test/budget.py"]]})
        for name, body in (("helper.py", HINTS), ("batch.py", HINTS), ("helper.mjs", MJS), ("SKILL.md", "# demo\nRun helper.py for every call.\n")):
            Path(self.repo, name).write_text(body)
        self.src = os.path.join(self.tmp, "projects", "-Users-me-Documents-demo")
        self.write(os.path.join(self.src, "S1.jsonl"), TRANSCRIPT)
        # A worker in a subagent transcript hits the same font error: one cluster, two places.
        self.write(os.path.join(self.src, "S1", "subagents", "agent-w.jsonl"), [
            use("w1", "2026-10-30T10:05:00Z", "Bash", {"command": RUN}),
            result("w1", "2026-10-30T10:05:01Z", '✗ Evaluation error: in set_characters: Cannot write to node with unloaded font "SF Pro"', True)])
        self.write(os.path.join(self.tmp, "projects", "-Users-me-Documents-perch", "P1.jsonl"), [
            use("p1", "2025-01-01T00:00:00Z", "mcp__perch__click", {"selector": "#a"}),
            result("p1", "2025-01-01T00:00:01Z", "tab_not_visible: the tab is hidden", True)])
        self.journal = os.path.join(self.tmp, "journal")
        self.write(os.path.join(self.journal, "2026-10-30.jsonl"), [
            {"ts": "2026-10-30T07:00:00-0300", "rid": "r1", "tool": "helper.py", "ok": False,
             "error": "Error: in set_layoutSizingHorizontal: FILL can only be set on children of auto-layout frames", "hint": "hint: x"},
            {"ts": "2026-10-30T07:00:01-0300", "rid": "r2", "tool": "helper.py", "ok": True, "result": "1"}])

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def config(self, cfg):
        os.makedirs(os.path.join(self.repo, "bench"), exist_ok=True)
        Path(self.repo, "bench", "learn.json").write_text(json.dumps(cfg))

    def write(self, path, rows):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.writelines(json.dumps(r) + "\n" for r in rows)

    def learn(self, *args, code=0, lessons=None, env=None):
        env = {**os.environ, "FIUM_HOME": self.home, **(env or {})}
        if lessons is not None:
            env["FIUM_LEARN_LESSONS"] = lessons
        r = subprocess.run([sys.executable, str(FIUM), "learn", "--repo", self.repo, *args], capture_output=True, text=True, env=env, cwd=self.tmp)
        self.assertEqual(r.returncode, code, r.stdout + r.stderr)
        return r.stdout + r.stderr

    def mine(self, *extra):
        out = os.path.join(self.tmp, "signals.jsonl")
        self.learn("mine", "--source", os.path.join(self.tmp, "projects"), "--source", self.journal, "--out", out, *extra)
        return [json.loads(l) for l in Path(out).read_text().splitlines()]

    def lessons(self, rows):
        path = os.path.join(self.tmp, "lessons.jsonl")
        self.write(path, rows)
        return path

    def test_mine_reads_every_kind_of_signal_with_its_evidence(self):
        sig = self.mine("--since", "2026-10-01")
        self.assertEqual(sorted({s["kind"] for s in sig}), ["correction", "error", "heavy", "retry", "slow"])
        errs = [s for s in sig if s["kind"] == "error"]
        self.assertEqual(len(errs), 4)  # 2 in the main session, 1 in the worker, 1 from the journal
        font = [s for s in errs if "unloaded font" in s["sig"]]
        self.assertEqual({s["sig"] for s in font}, {FONT_SIG})
        self.assertEqual((font[0]["session"], font[0]["project"], font[0]["shape"]), ("S1", "demo", "helper.py"))
        self.assertTrue(font[0]["ts"].startswith("2026-10-30T10:00:06"))
        self.assertTrue(any(s["source"] == "journal" and s["project"] == "demo" for s in errs))
        slow = [s for s in sig if s["kind"] == "slow"]
        self.assertEqual([(s["shape"], s["value"]) for s in slow], [("helper.py", 85.0)])  # Agent waits are not stalls
        self.assertEqual([(s["shape"], s["value"]) for s in sig if s["kind"] == "heavy"], [("Read lib.js", 30000)])
        self.assertEqual([(s["shape"], s["value"]) for s in sig if s["kind"] == "retry"], [("helper.py", 3)])
        corr = [s for s in sig if s["kind"] == "correction"]
        self.assertEqual(len(corr), 2)
        self.assertIn("don't rebuild the header", corr[0]["text"])
        self.assertEqual(corr[0]["after"], "Agent")
        self.assertEqual(corr[1]["sig"], "interrupted")

    def test_mine_reads_eval_stream_json_and_kept_journals(self):
        run = os.path.join(self.tmp, "run")
        rep = [dict(r, session_id="rep-0") for r in ([
            use("e1", "2026-10-30T11:00:00Z", "Bash", {"command": "S=/tmp/x; cd /tmp && cat references/building.md | head -50"}),
            result("e1", "2026-10-30T11:00:01Z", "Exit code 1\nTraceback (most recent call last):\n  File \"x.py\", line 3\nKeyError: 'id'", True),
            use("e2", "2026-10-30T11:00:02Z", "Bash", {"command": "python3 helper.py --recover 3f9aac0c1f2a"}),
            result("e2", "2026-10-30T11:00:03Z", "request 3f9aac0c1f2a is still running in the page; helper.py --recover 3f9aac0c1f2a", True)])]
        for r in rep:
            r.pop("sessionId")
        self.write(os.path.join(run, "r1_tx", "layout-1.jsonl"), rep)
        self.write(os.path.join(run, "r1_tx", "layout-1", "journal", "2026-10-30.jsonl"), [
            {"ts": "2026-10-30T08:00:00-0300", "rid": "j1", "tool": "batch.py", "ok": False, "error": "Error: in appendChild: oops"}])
        out = os.path.join(self.tmp, "eval.jsonl")
        self.learn("mine", "--all", "--source", run, "--out", out)
        errs = {s["sig"]: s for s in map(json.loads, Path(out).read_text().splitlines()) if s["kind"] == "error"}
        self.assertEqual(sorted(errs), ["error: in appendchild: oops", "keyerror: <s>",
                                        "request <hex> is still running in the page; helper.py --recover <hex>"])
        self.assertEqual((errs["keyerror: <s>"]["session"], errs["keyerror: <s>"]["shape"]), ("rep-0", "cat"))
        self.assertEqual(errs["error: in appendchild: oops"]["source"], "journal")

    def test_mine_since_drops_older_sessions(self):
        self.assertFalse([s for s in self.mine("--since", "2026-10-01") if s["project"] == "perch"])
        sig = self.mine("--since", "2024-01-01")
        self.assertEqual([s["sig"] for s in sig if s["project"] == "perch"], ["tab_not_visible: the tab is hidden"])

    def test_mine_reads_the_configured_projects_and_journals_by_default(self):
        self.config({"projects": ["zebra"], "journals": [self.journal]})
        projects = os.path.join(self.tmp, "home", ".claude", "projects")
        self.write(os.path.join(projects, "-Users-me-Documents-zebra", "Z.jsonl"), TRANSCRIPT)
        self.write(os.path.join(projects, "-Users-me-Documents-other", "O.jsonl"), TRANSCRIPT)
        self.learn("mine", "--since", "2026-10-01", env={"HOME": os.path.join(self.tmp, "home")})
        days = os.listdir(os.path.join(self.home, "learn", "demo"))
        sig = [json.loads(l) for l in Path(self.home, "learn", "demo", days[0], "signals.jsonl").read_text().splitlines()]
        self.assertEqual({s["project"] for s in sig}, {"zebra"})
        self.assertEqual(sum(s["kind"] == "error" for s in sig), 3)  # 2 from the zebra transcript, 1 from the journal

    def test_mine_tools_keeps_only_matching_calls_and_names_what_came_next(self):
        # A consumer project's session: perch fails, the agent works around it with Bash, which also fails.
        self.config({"projects": ["demo"], "tools": "^mcp__perch__"})
        self.write(os.path.join(self.src, "S1.jsonl"), [
            use("c1", "2026-10-30T10:00:00Z", "mcp__perch__click", {"selector": "#go"}),
            result("c1", "2026-10-30T10:00:01Z", "tab_not_visible: the tab is hidden", True),
            use("c2", "2026-10-30T10:00:02Z", "Bash", {"command": "osascript -e 'tell application \"System Events\" to x'"}),
            result("c2", "2026-10-30T10:00:03Z", "Exit code 1\nexecution error", True),
            human("2026-10-30T10:00:04Z", "no, don't steal focus"),
            use("c3", "2026-10-30T10:00:05Z", "mcp__perch__click", {"selector": "#go"}),
            result("c3", "2026-10-30T10:00:06Z", "tab_not_visible: the tab is hidden", True),
            use("c4", "2026-10-30T10:00:07Z", "mcp__perch__activate_tab", {}),
            result("c4", "2026-10-30T10:00:08Z", "ok"),
            human("2026-10-30T10:00:09Z", "stop clicking"),
        ])
        os.remove(os.path.join(self.src, "S1", "subagents", "agent-w.jsonl"))
        out = os.path.join(self.tmp, "signals.jsonl")
        self.learn("mine", "--all", "--source", self.src, "--out", out)
        sig = [json.loads(l) for l in Path(out).read_text().splitlines()]
        errs = [s for s in sig if s["kind"] == "error"]
        self.assertEqual([(s["shape"], s["next"]) for s in errs], [("click", "osascript"), ("click", "activate_tab")])
        self.assertEqual([s["text"] for s in sig if s["kind"] == "correction"], ["stop clicking"])
        self.assertEqual([(s["shape"], s["value"]) for s in sig if s["kind"] == "retry"], [("click", 2)])
        self.learn("digest", out, "--json", os.path.join(self.tmp, "d.json"), lessons=self.lessons([]))
        click = next(c for c in json.loads(Path(self.tmp, "d.json").read_text())["all"] if c["kind"] == "error")
        self.assertEqual(click["next"], {"osascript": 1, "activate_tab": 1})
        self.assertIn("tools", self.learn("--help"))

    def test_mine_reads_mid_turn_messages_and_design_corrections(self):
        # A design session: the user corrects while the agent works (queued, absorbed mid-turn)
        # and in words that don't start with "no" or "don't".
        def queued(ts, text):
            return {"type": "attachment", "timestamp": ts, "sessionId": "S1",
                    "attachment": {"type": "queued_command", "prompt": text, "origin": {"kind": "human"}, "humanTurn": True}}
        self.write(os.path.join(self.src, "S1.jsonl"), [
            human("2026-11-07T19:00:00Z", "explore a logo with bags of letters"),
            use("d1", "2026-11-07T19:00:05Z", "Write", {"file_path": "gen.py"}),
            queued("2026-11-07T19:01:00Z", "the shape of the bag follows its content, its not a tote"),
            queued("2026-11-07T19:02:00Z", "we're doing a plastic bag, not a purse"),
            result("d1", "2026-11-07T19:02:30Z", "ok"),
            human("2026-11-07T19:03:00Z", "nooooo"),
            human("2026-11-07T19:04:00Z", "ewww, the shapes are bad"),
            human("2026-11-07T19:05:00Z", "you should not have misread me"),
            human("2026-11-07T19:06:00Z", "b-spectrum is not good, ugly"),
            human("2026-11-07T19:07:00Z", "yes, much better, they can be rotated"),
            queued("2026-11-07T19:08:00Z", "and simpler shapes"),
            human("2026-11-07T19:09:00Z", "Build all three"),
            # the app puts a reminder before the person's words; a compaction summary is not a person
            human("2026-11-07T19:10:00Z", [{"type": "text", "text": "<system-reminder>\nLinked sessions now\n</system-reminder>"},
                                           {"type": "text", "text": "nooo, the stacked squares are wrong"}]),
            human("2026-11-07T19:11:00Z", "This session is being continued from a previous conversation that ran out of context. "
                                          "The user said it is not good"),
        ])
        os.remove(os.path.join(self.src, "S1", "subagents", "agent-w.jsonl"))
        # a forked session copies the same turns into a second transcript: count them once
        shutil.copy(os.path.join(self.src, "S1.jsonl"), os.path.join(self.src, "S1-fork.jsonl"))
        out = os.path.join(self.tmp, "signals.jsonl")
        self.learn("mine", "--all", "--source", self.src, "--out", out)
        corr = [s["text"] for s in map(json.loads, Path(out).read_text().splitlines()) if s["kind"] == "correction"]
        self.assertEqual(corr, ["the shape of the bag follows its content, its not a tote", "we're doing a plastic bag, not a purse",
                                "nooooo", "ewww, the shapes are bad", "you should not have misread me", "b-spectrum is not good, ugly",
                                "nooo, the stacked squares are wrong"])

    def test_help_defines_every_config_key_and_flag(self):
        out = self.learn("--help")
        self.assertNotIn("see RULES.md", out, "RULES.md doesn't define learn.json's keys; the help must")
        keys = set(re.findall(r'CFG(?:\.get\(|\[)"(\w+)"', Path(FIUM.parent, "learn.py").read_text()))
        for k in keys:
            self.assertRegex(out, rf"(?m)^  {k}\s+\S", f"{k} is read from bench/learn.json but the help doesn't say what it is")
        sys.path.insert(0, str(FIUM.parent)); import learn
        for name, sub in next(a for a in learn.parser()._actions if a.choices).choices.items():
            for a in sub._actions:
                if a.dest != "help":
                    self.assertTrue(a.help, f"fium learn {name} {a.option_strings or a.dest} has no help")

    def test_mine_reads_a_json_result_by_its_own_error(self):
        self.write(os.path.join(self.src, "S1.jsonl"), [
            use("j1", "2026-10-30T10:00:00Z", "mcp__perch__select", {"value": "Peru"}),
            result("j1", "2026-10-30T10:00:01Z", json.dumps({"ok": False, "error": "no matching option after open", "candidates": ["Chile"]})),
            use("j2", "2026-10-30T10:00:02Z", "mcp__perch__eval_js", {"js": "x.click()"}),
            result("j2", "2026-10-30T10:00:03Z", json.dumps({"__perch_error": "Cannot read properties of null (reading 'click')",
                                                             "__perch_error_name": "TypeError"}), True),
            use("j3", "2026-10-30T10:00:04Z", "mcp__perch__file_upload", {"path": "/x/cv.pdf"}),
            result("j3", "2026-10-30T10:00:05Z", json.dumps({"ok": False, "name": "cv.pdf", "size": 3})),
            use("j4", "2026-10-30T10:00:06Z", "mcp__perch__eval_js", {"js": "1"}),
            result("j4", "2026-10-30T10:00:07Z", json.dumps({"ok": True, "value": 1}))])
        os.remove(os.path.join(self.src, "S1", "subagents", "agent-w.jsonl"))
        out = os.path.join(self.tmp, "signals.jsonl")
        self.learn("mine", "--all", "--source", self.src, "--out", out)
        self.assertEqual([s["sig"] for s in map(json.loads, Path(out).read_text().splitlines()) if s["kind"] == "error"],
                         ["no matching option after open", "cannot read properties of null (reading <s>)", "file_upload: ok false"])

    def test_digest_clusters_ranks_and_marks_what_is_already_known(self):
        self.mine("--since", "2026-10-01")
        sigs = os.path.join(self.tmp, "signals.jsonl")
        lessons = self.lessons([{"id": "fill-hint", "kind": "hint", "signature": "error: in set_layoutsizinghorizontal: fill can only be set on children of auto-layout frames",
                                 "error": "FILL can only be set on children of auto-layout", "expect": "appendChild", "added": "2026-10-29"}])
        out = os.path.join(self.tmp, "digest.json")
        self.learn("digest", sigs, "--json", out, "--top", "3", "--explore", "0", lessons=lessons)
        d = json.loads(Path(out).read_text())
        top = d["clusters"]
        # The consolidated lesson's signal came back after the lesson was added: a relapse ranks first.
        self.assertEqual((top[0]["status"], top[0]["lesson"]), ("relapse", "fill-hint"))
        font = next(c for c in d["all"] if "unloaded font" in c["sig"])
        self.assertEqual((font["count"], font["sessions"], font["status"]), (3, 1, "hinted"))
        self.assertEqual(font["target"], "agent-ignored-doc: move the rule to the point of use (hint fires but the call repeats)")
        self.assertEqual((len(font["evidence"]), font["evidence"][0]["session"]), (3, "S1"))
        self.assertEqual(len(top), 3)
        self.assertIn("| relapse |", self.learn("digest", sigs, "--top", "3", "--explore", "0", lessons=lessons))

    def test_digest_marks_closed_known_cases_as_ledger(self):
        self.mine("--since", "2026-10-01")
        Path(self.repo, "ledger").mkdir()
        Path(self.repo, "ledger", "a.json").write_text(json.dumps({"signature": "interrupted", "status": "merged"}))
        Path(self.repo, "open.jsonl").write_text(json.dumps({"signature": "slow: helper.py", "status": "open"}) + "\n")
        self.config({"projects": ["demo"], "hints": ["helper.py"], "known": ["ledger", "open.jsonl"]})
        out = os.path.join(self.tmp, "digest.json")
        self.learn("digest", os.path.join(self.tmp, "signals.jsonl"), "--json", out, lessons=self.lessons([]))
        status = {c["sig"]: c["status"] for c in json.loads(Path(out).read_text())["all"]}
        self.assertEqual((status["interrupted"], status["slow: helper.py"]), ("ledger", "new"))

    def test_digest_explore_adds_random_unknowns_reproducibly(self):
        self.mine("--since", "2026-10-01")
        sigs, lessons = os.path.join(self.tmp, "signals.jsonl"), self.lessons([])
        a, b = (os.path.join(self.tmp, n) for n in ("a.json", "b.json"))
        self.learn("digest", sigs, "--json", a, "--top", "1", "--explore", "2", "--seed", "7", lessons=lessons)
        self.learn("digest", sigs, "--json", b, "--top", "1", "--explore", "2", "--seed", "7", lessons=lessons)
        da, db = json.loads(Path(a).read_text()), json.loads(Path(b).read_text())
        self.assertEqual(da["clusters"], db["clusters"])
        self.assertEqual([c["pick"] for c in da["clusters"]], ["top", "explore", "explore"])

    def test_replay_checks_each_lesson_against_every_helper_and_the_docs(self):
        ok = self.lessons([
            {"id": "font", "kind": "hint", "error": 'Error: in set_characters: Cannot write to node with unloaded font "Inter"', "expect": "loadFontAsync"},
            {"id": "skill-rule", "kind": "doc", "file": "SKILL.md", "expect": "helper.py"}])
        self.assertIn("2 lessons hold", self.learn("replay", lessons=ok))
        bad = self.lessons([
            {"id": "gone", "kind": "hint", "error": "Error: something nobody hints", "expect": "anything"},
            {"id": "deleted-rule", "kind": "doc", "file": "SKILL.md", "expect": "a rule nobody wrote \\d{9}"}])
        out = self.learn("replay", code=1, lessons=bad)
        self.assertIn("gone", out)
        self.assertIn("deleted-rule", out)

    def test_learn_appends_a_lesson_that_replay_then_holds(self):
        path = self.lessons([])
        self.learn("keep", "--id", "font", "--kind", "hint", "--error", 'unloaded font "X"', "--expect", "loadFontAsync",
                   "--signature", FONT_SIG, "--evidence", "S1 2026-10-30T10:00:06Z", lessons=path)
        rows = [json.loads(l) for l in Path(path).read_text().splitlines()]
        self.assertEqual(rows[0]["id"], "font")
        self.assertTrue(rows[0]["added"])
        self.assertIn("unknown kind", self.learn("keep", "--id", "x", "--kind", "vibe", "--expect", "y", code=2, lessons=path))
        self.assertIn("already", self.learn("keep", "--id", "font", "--kind", "hint", "--error", "e", "--expect", "y", code=2, lessons=path))
        self.assertIn("1 lessons hold", self.learn("replay", lessons=path))

    def test_learn_refuses_a_lesson_whose_fix_has_not_landed(self):
        path = self.lessons([])
        out = self.learn("keep", "--id", "x", "--kind", "hint", "--error", "Error: something nobody hints", "--expect", "anything",
                         code=2, lessons=path)
        self.assertIn("no fix in place", out)
        doc = os.path.join(self.tmp, "doc.md")
        Path(doc).write_text("# Rules\n- Load every font before writing text.\n")
        self.assertIn("no fix in place", self.learn("keep", "--id", "y", "--kind", "doc", "--file", doc, "--expect", "a rule nobody wrote",
                                                    code=2, lessons=path))
        self.assertIn("kept", self.learn("keep", "--id", "z", "--kind", "doc", "--file", doc, "--expect", "Load every font", lessons=path))

    def test_learn_refuses_a_negative_claim_and_accepts_one_that_names_the_way_through(self):
        path = self.lessons([])
        doc = os.path.join(self.tmp, "doc.md")
        Path(doc).write_text("- Screenshots in Arc don't work.\n"
                             "- figma.getVariableById is broken.\n"
                             "- The sync API doesn't work on dynamic pages; use getNodeByIdAsync instead.\n")
        for i, expect in enumerate(("Screenshots in Arc", "getVariableById is broken")):
            out = self.learn("keep", "--id", f"neg{i}", "--kind", "doc", "--file", doc, "--expect", expect, code=2, lessons=path)
            self.assertIn("negative claim", out)
        self.assertIn("kept", self.learn("keep", "--id", "ok", "--kind", "doc", "--file", doc, "--expect", "sync API", lessons=path))

    def test_digest_stale_lists_hints_and_lessons_that_never_fired_with_their_place(self):
        # The transcript's font errors fire the unloaded-font row, the journal fires the FILL row and
        # the hidden-tab hint shows in a tool result; the rest of the table never fired.
        self.write(os.path.join(self.src, "S2.jsonl"), [
            use("h1", "2026-10-30T11:00:00Z", "Bash", {"command": "python3 helper.py -e x"}),
            result("h1", "2026-10-30T11:00:01Z", "Exit code 1\nThe tab is hidden (document.visibilityState is hidden), and Chrome throttles", True),
            use("h2", "2026-10-30T11:00:02Z", "Read", {"file_path": "/x/helper.py"}),
            result("h2", "2026-10-30T11:00:03Z", "(r'must be in the same page as the parent', 'nodes on two pages')"),
            # A batch whose call exited 0 still reports one item's error.
            use("h3", "2026-10-30T11:00:04Z", "Bash", {"command": "python3 batch.py a.js b.js"}),
            result("h3", "2026-10-30T11:00:05Z", "a.js ok\n\t✗ Evaluation error: Error: in set_layoutSizingVertical: HUG can only be set on auto-layout frames")])
        path = self.lessons([
            {"id": "font", "kind": "hint", "error": 'unloaded font "X"', "expect": "loadFontAsync", "signature": FONT_SIG},
            {"id": "never", "kind": "hint", "error": "must be in the same page as the parent", "expect": "two pages",
             "signature": "error: must be in the same page as the parent"},
            {"id": "nosig", "kind": "doc", "file": "SKILL.md", "expect": "helper"}])
        out = self.learn("digest", "--stale", "--source", os.path.join(self.tmp, "projects"), "--source", self.journal, lessons=path)
        never = out.split("## Never fired", 1)[1].split("##", 1)[0]
        self.assertRegex(never, r"helper\.py:\d+ .*must be in the same page")
        self.assertRegex(never, r"batch\.py:\d+ .*must be in the same page")
        self.assertRegex(never, r"lessons\.jsonl:2 .*never")
        self.assertRegex(never, r"helper\.mjs:\d+ .*UNDEFINED_HINT")
        for fired in ("unloaded font", "FILL can only", "HUG can only", "HIDDEN_HINT", "lessons.jsonl:1 "):
            self.assertNotIn(fired, never)
        self.assertRegex(out.split("## Unmeasured", 1)[1], r"lessons\.jsonl:3 .*nosig")

    def test_check_dry_run_lists_the_gates(self):
        out = self.learn("check", "--dry-run", "--candidate", "cand.json")
        for gate in ("python3 -m unittest", "test/budget.py", "replay", "compare bench/baseline.json cand.json"):
            self.assertIn(gate, out)
        out = self.learn("check", "--dry-run")
        self.assertIn("replay", out)
        self.assertNotIn("compare bench", out)

    def test_check_judges_a_live_run_with_the_projects_own_gate(self):
        self.config({"gates": [], "live_gate": ["python3", "tests/eval/gate.py"], "baseline": "tests/eval/baseline.json"})
        out = self.learn("check", "--dry-run", "--candidate", "cand.json")
        self.assertIn("$ python3 tests/eval/gate.py tests/eval/baseline.json cand.json", out)
        self.assertNotIn("compare", out)


if __name__ == "__main__":
    unittest.main()
