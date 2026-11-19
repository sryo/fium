"""replycheck: a turn-end hook that sends back a reply carrying a rule's id, a goal's number or a cap's level (W4), or one
that landed a change while fium done's last word on it was that it isn't done (W3, K3)."""
import json, re, sys
from pathlib import Path

import datetime

from learn import NOT_DONE, NOT_THE_USER, landing, parse_ts, runs_done

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


def saved_for(cwd):
    # The verdict fium done saved for the checkout the session works in.
    import subprocess
    from done import saved_verdict
    top = subprocess.run(["git", "-C", cwd or ".", "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip()
    return saved_verdict(Path(top)) if top else None


def landed_unheard(lines, saved=lambda: None):
    # fium done's not-done lines when a push or merge followed them with neither its "can merge" nor the user in between.
    # A run whose output the agent never saw (sent to a file, filtered to nothing) is read from its saved verdict.
    uses, unheard, hit, blind = {}, None, None, False
    for line in lines:
        try:
            row = json.loads(line)
            m = row.get("message") or {}
        except (ValueError, AttributeError):
            continue
        c = m.get("content")
        blocks = [{"type": "text", "text": c}] if isinstance(c, str) else c if isinstance(c, list) else []
        said = " ".join(b.get("text", "") for b in blocks if isinstance(b, dict) and b.get("type") == "text").strip()
        if m.get("role") == "user" and said and not NOT_THE_USER.match(said) and not row.get("isMeta"):
            unheard, hit, blind = None, None, False
        for b in blocks:
            if not isinstance(b, dict):
                continue
            if b.get("type") == "tool_use" and b.get("name") == "Bash":
                uses[b.get("id")] = (b.get("input") or {}).get("command", "")
            elif b.get("type") == "tool_result" and b.get("tool_use_id") in uses:
                cmd, out = uses.pop(b["tool_use_id"]), b.get("content")
                out = out if isinstance(out, str) else " ".join(x.get("text", "") for x in out or [] if isinstance(x, dict))
                if runs_done(cmd):
                    said = [l.strip() for l in out.splitlines() if NOT_DONE.search(l)]
                    blind = "it can merge" not in out and not said
                    unheard = None if "it can merge" in out else " ".join(said[:3]) or unheard
                if landing(cmd) and blind and not unheard:
                    # Only a verdict saved before this landing is the one it landed on.
                    v, when = saved(), parse_ts(row.get("timestamp")) or datetime.datetime.now(datetime.timezone.utc)
                    v = v if v and (parse_ts(v.get("at")) or when) <= when else None
                    unheard, blind = (" ".join(v["said"][-3:]) if v and v.get("code") else None), False
                if unheard and landing(cmd):
                    hit = unheard
    return hit


def verdict(hook, ids):
    # stop_hook_active: this turn end follows a reply the hook already sent back; once is enough.
    if hook.get("stop_hook_active"):
        return None
    try:
        lines = Path(hook.get("transcript_path", "")).read_text().splitlines()
    except OSError:
        lines = []
    landed = landed_unheard(lines, lambda: saved_for(hook.get("cwd")))
    if landed:
        return {"decision": "block", "reason": "This change went in while fium done's last word on it was that it isn't done: %s "
                "Tell the user plainly that it isn't done and what is left, then fix it and run fium done again, or ask them whether "
                "it can go in as it is." % landed}
    text = hook.get("last_assistant_message")
    if text is None:
        if not lines:
            return None
        text = turn_text(lines)
    hits = list(dict.fromkeys(found(text, ids)))
    if not hits:
        return None
    return {"decision": "block", "reason": "Your reply to the user has %s. Say it again in their words: a rule by what it says, a goal by its name, "
            "a cap by what it allows. Correct it in one short message, not a repeat of the whole reply. If one of these isn't a fium id, say so and stop."
            % ", ".join(hits)}


def replycheck_main():
    try:
        v = verdict(json.load(sys.stdin), rule_ids())
    except Exception:
        # A turn-end hook in every session: a fault here never stops one.
        return 0
    if v:
        print(json.dumps(v))
    return 0
