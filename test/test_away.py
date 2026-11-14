import unittest
from away import away

IDLE = '    | |   "HIDIdleTime" = %d\n'
HOLD = '   pid 77(%s): [0x1] 00:10:21 %s named: "x"\n'


class Away(unittest.TestCase):
    # L3: a check that takes the front runs only while the user is away.
    def test_locked_is_away_whatever_else(self):
        self.assertEqual(away(IDLE % 0, '"CGSSessionScreenIsLocked"=Yes', HOLD % ("Arc Helper", "PreventUserIdleDisplaySleep")), (True, "the screen is locked"))

    def test_recent_input_is_present(self):
        self.assertEqual(away(IDLE % 12_000_000_000, "", ""), (False, "input 12s ago"))

    def test_five_quiet_minutes_is_away(self):
        self.assertEqual(away(IDLE % 301_000_000_000, "", ""), (True, "no input for 301s"))

    def test_a_playing_video_is_present_however_quiet(self):
        got = away(IDLE % 3_600_000_000_000, "", HOLD % ("Arc Helper", "PreventUserIdleDisplaySleep"))
        self.assertEqual(got, (False, "Arc Helper keeps the display awake"))

    def test_an_agents_caffeinate_and_system_holds_are_not_the_user(self):
        holds = HOLD % ("caffeinate", "PreventUserIdleDisplaySleep") + HOLD % ("Claude", "NoIdleSleepAssertion")
        self.assertEqual(away(IDLE % 400_000_000_000, "", holds)[0], True)

    def test_unreadable_idle_time_is_present(self):
        self.assertEqual(away("", "", ""), (False, "can't read the idle time"))


if __name__ == "__main__":
    unittest.main()
