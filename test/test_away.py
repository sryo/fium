import unittest
import re
from away import away, IDLE_JS

IDLE = '%d\n'
HOLD = '   pid 77(%s): [0x1] 00:10:21 %s named: "x"\n'


class Away(unittest.TestCase):
    # L3: a check that takes the front runs only while the user is away.
    def test_locked_is_away_whatever_else(self):
        self.assertEqual(away(IDLE % 0, '"CGSSessionScreenIsLocked"=Yes', HOLD % ("Arc Helper", "PreventUserIdleDisplaySleep")), (True, "the screen is locked"))

    def test_recent_input_is_present(self):
        self.assertEqual(away(IDLE % 12, "", ""), (False, "input 12s ago"))

    def test_five_quiet_minutes_is_away(self):
        self.assertEqual(away(IDLE % 301, "", ""), (True, "no input for 301s"))

    def test_a_playing_video_is_present_however_quiet(self):
        got = away(IDLE % 3600, "", HOLD % ("Arc Helper", "PreventUserIdleDisplaySleep"))
        self.assertEqual(got, (False, "Arc Helper keeps the display awake"))

    def test_an_agents_caffeinate_and_system_holds_are_not_the_user(self):
        holds = HOLD % ("caffeinate", "PreventUserIdleDisplaySleep") + HOLD % ("Claude", "NoIdleSleepAssertion")
        self.assertEqual(away(IDLE % 400, "", holds)[0], True)

    # HIDIdleTime and the any-event counter also count null events, which a
    # process's first posted event and other background work reset every few
    # seconds: they said "input 0s ago" with the user gone 45 minutes.
    def test_idle_is_the_newest_real_input_not_any_event(self):
        types = [int(t) for t in re.search(r"\[([\d, ]+)\]", IDLE_JS).group(1).split(",")]
        self.assertEqual(sorted(types), [1, 3, 5, 6, 7, 10, 12, 22, 23, 24, 25, 27])
        self.assertNotIn("4294967295", IDLE_JS)
        self.assertNotIn("HIDIdleTime", IDLE_JS)
        self.assertIn("CGEventSourceSecondsSinceLastEventType(1,", IDLE_JS)

    def test_fractional_seconds_round_down(self):
        self.assertEqual(away("299.9\n", "", ""), (False, "input 299s ago"))

    def test_unreadable_idle_time_is_present(self):
        self.assertEqual(away("", "", ""), (False, "can't read the idle time"))


if __name__ == "__main__":
    unittest.main()
