# fium rules

How every project here is laid out, measured and improved. Each rule has an id for reviews and commits to cite. `fium check` checks the rules marked ✓.

**P1 The aim.** Simple, cheap on resources, reasonably fast, never in the user's way. It settles any conflict between rules.

## Files (F)
- **F1 ✓** Every project has `AGENTS.md` (never `AGENT.md`) with how it's built and tested, `README.md` (R), `GOALS.md` (G), `LICENSE`, sryo's by default, and a `.gitignore` that lists `.DS_Store`.
- **F2 ✓** `CLAUDE.md` is a symlink to `AGENTS.md`.
- **F3** AGENTS.md says how to run the tests. templates/AGENTS.md puts it under `## Test`, but any heading in any language will do; `fium status --campaign` runs the first code block under a heading that names testing.
- **F4 ✓** A project's own checks go in `bench/checks`, one command per line; `fium check --all` fails the project when one fails. A line `when <glob> …: <command>` runs only when the change since the base branch touches a file one of its globs matches, so a check learned from one incident costs nothing elsewhere.

## Goals (G)
- **G1** GOALS.md says what the project is for, what is never traded, its goals as a numbered list in priority order, how each is measured, and its non-goals. templates/GOALS.md suggests headings; any wording or language will do.
- **G2 ✓** Every goal has a row in the metrics table, the first Markdown table after the numbered goals: Goal | Metric | Where | Run, headers in any language (Where or Dónde, Run, Correr or Comando are found by name, anything else by position). Where measures it, or "manual". Run is what `fium done` runs (K3): `` `cmd` ``, `` costly: `cmd` `` (only with `--costly`), `` live: `cmd` ``, or by hand (a mano), passing only on `fium done --by-hand` (W6). A command's last line is a run file (K1) or a number.

## README (R)
A README is for someone deciding whether they want this, and then using it. It says why it's useful and how to use it, in plain words. Use rooms, avis and perch as models.
- **R1 ✓** The opener is one or two sentences on what it lets you do and why you'd want it. Use second person, short sentences, no hype or jargon.
- **R2** Then the shortest way to get it and the few things a person actually types. templates/README.md calls them `## Install` and `## Use`; any heading in the README's language will do. Add works-with and known-gaps sections only when they have something to say.
- **R3 ✓** No build steps, dev setup or internals; those belong in AGENTS.md. Describe limits by what the user sees, not by how it works inside.

## Live runs (L)
- **L1** Before a live run, state its cost in tokens, turns and wall time, never dollars.
- **L2** A live run covers only the tasks `fium affects <base>..HEAD` names, at 2 reps; a third only when they disagree, 3 to refresh a baseline. Read the transcripts you have first and batch fixes into one run.
- **L3** A check that opens a window or drives a browser runs where the user isn't looking: headless, on a loft (perch `new_tab {loft:"WxH"}`) or in a room. Never in their tabs, windows or front app; looking at a screen (W6) counts. One that has to take the front (a device, another app) runs `fium away` first and goes on only when it exits 0; otherwise it stops and its row reads as not measured.

## Cost (K)
A change is done when the user has seen what it did to each of the project's own metrics and says it can merge. `fium done` measures them; something that broke or crossed a limit blocks it.
- **K1** A bench writes `{"metrics": {name: {"dir": "lower"|"higher", "kind", "samples": [...]}}, "limits": {name: line}}`, stamped with `"commit"` (HEAD) and `"dirty"`, and an agent's run with `"env": {"model", "claude_code_version"}`. Time and tokens are noisy; set `"noisy": true` on anything else that varies between identical runs. `fium noise` sets the band from an A/A run.
- **K2** Commit before you measure: `fium compare` blocks a run from a dirty tree or another commit, unless everything changed since matches `bench/inert` or its defaults (human docs, tests, noise and baseline files). Never list agent-facing docs (SKILL.md, `references/`) there: they change what a run measures.
- **K3 ✓** The user decides when a change is done, in the conversation, never in commits or files. `fium done` measures every How we know row at the base and now, each held to its cap (K5); on the plan's yes, `fium done --start` reads the live rows' before. A project with goals says in AGENTS.md that a change is done when `fium done` says so.
- **K4** A change that only cuts needs nothing worse. One that adds code needs a better number, or a new How we know row running it the way the user does, to what they see, each fallback included. Use the cheapest run that would catch the error: their command or call, headless. Cheap is the default, never a reason to miss an error: a window, browser, device or end-to-end flow when nothing cheaper reaches it (`live:`), that one flow alone, never the whole suite. More passing tests isn't that number. A cut nothing measures isn't kept. Refresh the baseline only in its own commit.
- **K5** Only the user writes the `Caps:` line under GOALS.md's How we know: `kind=level` entries (kind is `quality`, `tokens`, `count`, `loc`, `bytes`, `time`, `all` or a metric glob; the last match wins), like `all=ask quality=hard bytes=ask+10%`. `hard`: not done until the number is the same or better, or the user agrees it can't be without lowering quality. `ask`, the default: a move within its margin (`ask+10%`, `ask+200`; none unless written) passes, past it the user decides. `free`: shown only. A set external limit (Cloudflare's free tier) is a baseline `limit` (K1). A change is held to the base's caps and row commands, never to ones it wrote: `fium done` asks the user about a change to the Caps line, a row's command or a bench file (`bench/judge`, else `bench/*` and the baseline and noise files).

## Work (W)
How a change goes from an idea to done.
- **W1** Read the repo, then reply once: the plan (`R1…Rn`, each a result and the test that shows it, an R for each README or GOALS promise asked for, what's out, the numbers it moves, and each added path's fallbacks and what the screen shows after) and at most three questions, each with a default. Numbers, not adjectives. The user's yes takes the defaults and freezes the plan (K3).
- **W2 ✓** Test first: each R's test names it and fails before the code; a fix starts with one that fails on the bug, or, for a doc or message, a check that it stays. Never edit an expectation to fit the code. A flaky test is never rerun until it passes, slept on or skipped: find why it flakes, or delete it and say why.
- **W3** One goal, about 100 lines besides tests; "for now" is another change. Done is every R green and its row (K4) run for real, checked against what the user first asked; for a project or its README, every promise in README and GOALS, built and measured or cut on the user's OK. Until then, keep working without asking. A problem the change caused is never deferred.
- **W4** Tell the user things in their words: a goal by its name, a rule by what it says, each number with what it measures and its before → after. Never a goal's number, a rule's id or a cap's level. Say which paths ran for real.
- **W5** The project is yours while you work in it, not only your change. Once the user says done (K3), landing it is yours too, without asking: commit, merge, push, clear its branches and worktrees. "Merge" means every branch: merge it or discard it if stale, keeping what passes, and say which. Only the user decides done, the caps (K5), and anything that deletes their data or rewrites history.
- **W6** For a change that replaces or restructures something users see, before you change it list what the old one showed and every place and size it shows (each screen, width, theme and state). After, look at each one again and record what it shows now: `fium done --by-hand "<row>" "<the list>"`. Without that list for the current tree, a by-hand row stays open; one whose Where names paths (`src/ui/*`) waits only on a change to them.
- **W7** Anything several agents or processes can call at once gets a test with several callers at once. A race shows only then.

## Learning (S)
- **S1** Put the fix where the agent is when it fails. An error message that names the fix beats a line in a doc. An error or empty state a user sees says what happened and what to do next. When a failure comes back after its fix, move the fix closer to that point.

## Commits (C)
- **C1** Commit messages say what landed, in the style of the repo's recent `git log`.
