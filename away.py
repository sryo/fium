"""away: is the user away from this Mac? A check that takes the front runs only then (L3)."""
import re, subprocess, sys

AWAY_S = 300


def away(idle, root, holds):
    # idle: `ioreg -c IOHIDSystem`; root: `ioreg -n Root -d1`; holds: `pmset -g assertions`.
    if re.search(r'"CGSSessionScreenIsLocked"\s*=\s*Yes', root):
        return True, "the screen is locked"
    # A movie's viewer sends no input: whatever of theirs keeps the display awake says they're there.
    # caffeinate's holds are agents', not the user's.
    for name, kind in re.findall(r"pid \d+\(([^)]*)\): \[[^\]]*\] \S+ (\w+) named:", holds):
        if kind in ("PreventUserIdleDisplaySleep", "NoDisplaySleepAssertion") and name != "caffeinate":
            return False, f"{name} keeps the display awake"
    m = re.search(r'"HIDIdleTime" = (\d+)', idle)
    if not m:
        return False, "can't read the idle time"
    s = int(m.group(1)) // 1_000_000_000
    return (True, f"no input for {s}s") if s >= AWAY_S else (False, f"input {s}s ago")


def away_main():
    def out(*cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=10).stdout
        except (OSError, subprocess.TimeoutExpired):
            return ""
    gone, why = away(out("ioreg", "-c", "IOHIDSystem", "-d", "4"), out("ioreg", "-n", "Root", "-d", "1"), out("pmset", "-g", "assertions"))
    print(("away: " if gone else "present: ") + why)
    sys.exit(0 if gone else 1)
