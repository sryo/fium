"""replycheck: a turn-end hook that sends back a reply carrying a rule's id, a goal's number or a cap's level (W4)."""
import json, re, sys
from pathlib import Path

CAPS = r"\b(?:all|quality|tokens|count|loc|bytes|time)=(?:hard|ask|free)\b(?:\+\d+%?)?|\bask\+\d+%?"
GOAL = r"\bgoals?\s*#?\d+\b"


def rule_ids():
    # R ids are left out: a plan names its results R1…Rn (W1).
    return {i for i in re.findall(r"\*\*([A-Z]\d+)\b", (Path(__file__).parent / "RULES.md").read_text()) if i[0] != "R"}


def found(text, ids):
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    pat = "|".join([r"(?<![A-Za-z0-9])(?:%s)(?![A-Za-z0-9])" % "|".join(sorted(ids)), "(?i:%s)" % GOAL, CAPS])
    return [m.group(0) for m in re.finditer(pat, text)]


def turn_text(lines):
    # What the assistant wrote since the user last spoke; a tool result is a user entry too, but not theirs.
    out = []
    for line in lines:
        try:
            m = json.loads(line).get("message") or {}
        except (ValueError, AttributeError):
            continue
        c = m.get("content")
        blocks = [{"type": "text", "text": c}] if isinstance(c, str) else c if isinstance(c, list) else []
        texts = [b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text"]
        if m.get("role") == "user" and texts:
            out = []
        elif m.get("role") == "assistant":
            out += texts
    return "\n".join(out)


def verdict(hook, ids):
    # stop_hook_active: this turn end follows a reply the hook already sent back; once is enough.
    if hook.get("stop_hook_active"):
        return None
    text = hook.get("last_assistant_message")
    if text is None:
        try:
            text = turn_text(Path(hook.get("transcript_path", "")).read_text().splitlines())
        except OSError:
            return None
    hits = list(dict.fromkeys(found(text, ids)))
    if not hits:
        return None
    return {"decision": "block", "reason": "Your reply to the user has %s. Say it again in their words: a rule by what it says, a goal by its name, "
            "a cap by what it allows. Correct it in one short message, not a repeat of the whole reply. If one of these isn't a fium id, say so and stop."
            % ", ".join(hits)}


def replycheck_main():
    try:
        v = verdict(json.load(sys.stdin), rule_ids())
    except (ValueError, OSError):
        return 0
    if v:
        print(json.dumps(v))
    return 0
