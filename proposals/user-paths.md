# Proposal: a change that adds a user path isn't done until a row runs it end to end

Status: proposal for the user to approve. Nothing in RULES.md, SKILL.md or the code has changed.

## Verdict
Mostly a gap in fium. yapa's usage shows the gap but didn't cause it. yapa followed fium as written: every goal has a row, the benches run, tests come first, and `fium done` exited 0. fium never asks whether any row runs the path a change adds, the way a user does, all the way to what they see. So a feature whose only tests are units and dry runs passes.

## What happened (yapa, 2026-11-05)
You picked "Remove the 5" on the pad. che logged that the Claude app hadn't focused the session within 3 s and put the text on the clipboard, though `main.log` shows the app did focus it. The pad then switched between the reply and an option prompt with no options. The gate is in `~/Documents/yapa/mac/Sources/che/main.swift:58-77`: che needs the app in front *and* the last 64 KB of `main.log` to name the session, within 3 s.

### What yapa measured for this path
- Goal 3 promises "the words arrive in the session as text" (`yapa/GOALS.md:16`). Its only row (`GOALS.md:33`) is `bench/che`: latency and word error rate, and the script itself says "nothing is typed" (`bench/che:2-3`).
- Goal 2's live row, `bench/jeta-hook-live` (`GOALS.md:30`), covers permission hooks only. It has no `/say`, no option pick and no che.
- `test/che-say` posts only `/say?dry` (`test/che-say:13-19`). A dry post never opens a session, never waits for focus and never types.
- `test/che-talk` greps source strings (`test/che-talk:12-16`).
- `TalkTests.testR2` (commit c134af5) runs `focusedSession()` on a two-line string it made up. The real gate never ran against the real Claude app.
- `test/jeta-hooks-sim` covers permission and status hooks only.
- Never run by anything: pick → `/say` → deep link → focus → typed into the session; the clipboard fallback; what the pad shows after a failed delivery; the 169.254.x.x refusals in che.log.

### What fium requires, and where it stops
- **G2** (`RULES.md:15`): every goal has a row. `check.py:48` errors only when a goal has none, so one proxy row per goal passes.
- **K4** (`RULES.md:32`): "one that adds needs a better number". Nothing enforces it. `done.py:161-282` judges only rows that already exist. A change that adds a path no row measures reads "same" everywhere and exits 0. Only the loop enforces K4, with `--target` (`tries.py:67-83`).
- **W2** (`RULES.md:38`): tests come first, but any layer counts. Unit tests satisfy it.
- **W3** (`RULES.md:39`) and SKILL.md:35 ask for "one real run". It is singular, unrecorded and checked by no tool, and it says nothing about fallbacks or what the screen shows after.
- **S1** (`RULES.md:41`) says what a fallback must tell the user, but nothing makes anyone exercise one.
- across.md:29 says "unit tests miss wiring", but only for across-repo work.
- **A trap that pushes agents toward proxies.** The row fium should want is the hardest one to add today. A new `live:` row reads as "Couldn't measure (live: no before)" (`done.py:211`). A new bench that doesn't exist at the base reads "failed at the base" (`done.py:231-233`). Both keep the change open, while a dry row on an existing bench passes.

## Recommended change
Minimal (judge B's winner), with the trigger and grafts both judges agreed on. Rule count stays 22. About 40 LOC go into done.py, and RULES.md grows by about 250 B.

### Rules (reworded, none added)
- **K4** A change that only cuts needs nothing worse. One that adds code needs a better number, or a new How we know row that runs what it adds the way the user does: from their action to what they see, each fallback included, `live:` when it needs a device or another app. More passing tests isn't that number. `fium done` asks when neither is there. A cut nothing measures isn't kept. Refresh the baseline only in its own commit.
- **W1** gains about 15 words. The plan lists, for each path the change adds, each fallback and what the screen shows after each. Each one becomes a metric of K4's row.
- **W3** loses "one real run". Done is every R green and its row (K4) run for real. The real run is now recorded, and every later `fium done` repeats it.
- **W4** gains one clause: say which paths ran for real and which didn't.
- **SKILL.md** "Build a change" step 2 drops "one real run".

### Mechanism (`done.py`, test first in `test/test_done.py`)
1. **The ask.** `git diff --numstat <base>` counts net code lines the change adds. Tests, bench and docs don't count. Untracked files do (`git ls-files --others --exclude-standard`), and code is recognised by check.py's extensions. If the change adds 20 or more lines and no metric is better or new, done exits 3. "tests passing" (`done.py:63`) doesn't count. The message is placed where the agent stands (S1): "this adds code no number shows: add a How we know row that runs it the way the user does, each fallback and what the screen shows after, or ask the user."
2. **New rows pass.** A row or `live:` row added since the base prints as `new` with its reading, no longer as "Couldn't measure". This fixes `done.py:211` and `done.py:231-233`.
3. **Each path holds by K1 limits, not a new exception.** The row's bench writes one metric per path, each with a K1 `limit` (for example delivered = 1). The existing limit check then blocks a broken path, and Caps (K5) stays the user's.
4. **Dry-run warning.** A new row whose command or Where says `dry`, `--dry`, `stub` or `fake` gets a warning: "this row doesn't run it the way the user does".
5. **A dropped row is a cut.** A row in the base GOALS.md that is gone now counts as a cut nothing measures, so the ask can't be dodged by deleting rows.
6. **Doc test.** W3 and SKILL.md no longer say "one real run", and K4 names fallbacks and what the user sees after.

### What it would and wouldn't catch
- **The 3 s focus miss:** caught if the row really drives the Claude app. The first pick would have shown delivered = 0. A dry row still satisfies the ask, but it now draws a warning. A rare race needs reps.
- **The clipboard fallback:** likely caught, because the message and W1 ask for each fallback by name.
- **The empty-options screen:** caught only if the row reads the pad's screen after a failed delivery. The wording points there, but nothing checks it.
- **Can't do:** fium can't list a project's branches for it. Which paths exist is still the agent's judgment. The change makes leaving a path out visible, cheap to fix and hard to hide.
- **Cost to you:** about one exit-3 question on a code change that moves nothing, such as a refactor. You answer it in a word.

## For yapa, once this lands (proposal only; nothing in yapa was edited)
Goal 3's row measures a proxy. Add this:

| Goal | Metric | Where | Run |
|---|---|---|---|
| 3 | option picks typed into their session (limit: all); picks for a session the app lacks that land on the clipboard with the pad saying so; picks whose session didn't focus, same; after each, the pad shows the reply or the next prompt, never a prompt with no options; ms from pick to text in the session (p50); che refusals per run | `bench/che-live`: a scratch Claude app session, picks fired through jeta's real tap path to che's real `/say`, read back from the session's transcript, `pbpaste` and the pad's `buddy.log` | `live: bench/che-live` |

It also needs:
- `bench/che-live`, about 120 lines, built on `bench/jeta-hook-live`'s ssh code. It types into a scratch session only, never yours, and states its cost first (L1).
- jeta logging what Screen shows after a pick: whether the question still has options, and whether a note says where the text went.
- che taking its log path and timeout from the environment, so the bench can force the "didn't focus" path and the "not the app's" path.
- `bench/judge` listing `bench/che-live`, since it acts in the world.

## Proposals not chosen
A workflow ran five proposers and two judges. Judge A (would it catch the next incident) picked **paths** with done-gate's trigger. Judge B (fium fit and cost) picked **minimal**. The recommendation above is minimal, plus paths' per-path metrics expressed as K1 limits.
- **paths:** a `seen:` metric dialect in G2, each path held at 1, blocking regardless of Caps. Strongest once used. Not chosen as written: it is opt-in by the agent's judgment, which is how yapa failed; it adds a dialect; and it overrides K5. Its per-path metrics and dry warning were grafted.
- **done-gate:** K4 enforced from numstat at 10 lines. Almost the same as minimal. Its untracked-files counting and "tests passing isn't proof" were grafted. 10 lines nags too often (P1).
- **plan:** each path becomes an `# R` line in bench/checks, and done runs the lines a change adds. Not chosen: it gives bench/checks two meanings, its live lines never re-run after merge so they rot, and it rewrites three rules.
- **learn:** `fium done --start --path` records the plan's paths, and done lists the ones that never ran. Not chosen: the evidence is self-attested (a file's mtime), the state is machine-local, it adds two flags, and nothing is re-measured later. Its W4 clause was grafted.
