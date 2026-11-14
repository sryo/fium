import json, unittest
from replycheck import found, turn_text, verdict

IDS = {"P1", "L3", "W4", "W7", "K5", "G2"}


def entry(role, *blocks):
    return json.dumps({"type": role, "message": {"role": role, "content": list(blocks)}})


def text(s):
    return {"type": "text", "text": s}


class ReplyCheck(unittest.TestCase):
    # W4: a reply never carries a rule's id, a goal's number or a cap's level.
    def test_a_rule_id_is_found(self):
        self.assertEqual(found("52144cf: rules L3 and W7, fium away", IDS), ["L3", "W7"])

    def test_a_goal_number_and_a_cap_level_are_found(self):
        self.assertEqual(found("Goal 2 moved; quality=hard held and time is ask+10%", IDS), ["Goal 2", "quality=hard", "ask+10%"])

    def test_plain_words_pass(self):
        self.assertEqual(found("The windows-run-as-visible goal held; the time cap lets it move 10%. Asked hard questions, all free.", IDS), [])

    def test_ids_inside_other_words_and_plan_results_pass(self):
        self.assertEqual(found("R1 and R2 are green; see WL3X and the K50 chip", IDS), [])

    def test_fenced_code_is_skipped_inline_code_is_not(self):
        self.assertEqual(found("ran:\n```\n✔ K5: up wakes the display\n```\nand `W4` says so", IDS), ["W4"])

    def test_turn_text_is_what_the_assistant_wrote_since_the_user_last_spoke(self):
        lines = [
            entry("assistant", text("old L3")),
            entry("user", text("go on")),
            entry("assistant", text("first"), {"type": "tool_use", "name": "Bash", "input": {}}),
            entry("user", {"type": "tool_result", "content": "W7 in a tool result"}),
            "not json",
            entry("assistant", text("last")),
        ]
        self.assertEqual(turn_text(lines), "first\nlast")

    def test_a_hit_blocks_once_and_says_how_to_fix_it(self):
        v = verdict({"last_assistant_message": "rule W4 applies"}, IDS)
        self.assertEqual(v["decision"], "block")
        self.assertIn("W4", v["reason"])
        self.assertIn("by what it says", v["reason"])
        self.assertIsNone(verdict({"last_assistant_message": "rule W4 applies", "stop_hook_active": True}, IDS))
        self.assertIsNone(verdict({"last_assistant_message": "the rule about telling things in your words applies"}, IDS))


if __name__ == "__main__":
    unittest.main()
