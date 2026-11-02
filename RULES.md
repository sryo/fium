# fium rules

How every project here is laid out, measured and improved. Each rule has an id for reviews and commits to cite. `fium check` checks the rules marked ✓.

**P1 The aim.** Natural, simple ways of doing things that are cheap on resources, reasonably fast, and never get in the user's way. When two rules conflict, the reading that serves this aim wins.

## Files (F)
- **F1 ✓** `AGENTS.md` holds the agent instructions: how the project is built and tested. It is never named `AGENT.md`.
- **F2 ✓** `CLAUDE.md` is a symlink to `AGENTS.md`.
- **F3 ✓** `README.md`, following R.
- **F4 ✓** `GOALS.md`, following G.
- **F5 ✓** `LICENSE`. The default is the sryo license (fium's own).
- **F6 ✓** Agent docs (AGENTS.md, SKILL.md) have no `@` imports. When an import stops resolving, its text drops silently.
- **F7 ✓** AGENTS.md has a `## Test` section with the command that runs the tests.
- **F8 ✓** Checks fium can't know about (a doc budget, a copy test, a generated file rebuilt and diffed) go in `bench/checks`, one command per line. `fium check --all` runs them, and a failing one fails the project.

## Memory (M)
- **M1 ✓** Each memory file (`~/.claude/projects/<project>/memory/`) opens with `name` and `description` frontmatter, so an agent loads those lines and reads a body only when it needs it.

## Goals (G)
- **G1 ✓** GOALS.md has these sections:
  - What X is for
  - Never traded
  - Goals, in priority order (the higher goal wins a conflict)
  - How we know
  - Non-goals
- **G2 ✓** Every goal has a How we know row: Goal | Metric | Where | Run. Where is the command, test or file that measures it, or "manual" when nothing can measure it yet. Run is what `fium done` runs: `` `the command` `` at the base and now, `` costly: `…` `` the same but only with `--costly` (an agent eval), `` live: `…` `` on live state, now only, or by hand. A command's last line is a run file (K2) or a number.

## README (R)
A README is for someone deciding whether they want this, and then using it. It says why it's useful and how to use it, in plain words. Use rooms, avis and perch as models.
- **R1 ✓** The first line is `# name`, the repo name in lowercase. A skill you invoke may use `# /name`. A logo may stand in for it.
- **R2 ✓** The opener is one or two sentences on what it lets you do and why you'd want it. Use second person, short sentences, no hype or jargon. Describe limits by what the user sees, not by how it works inside.
- **R3 ✓** Then `## Install`, the shortest way to get it, and `## Use`, the few things a person actually types. Add `## Works with` and `## Known gaps` only when they have something to say.
- **R4 ✓** No badges.
- **R5 ✓** No build steps, dev setup or internals. Those belong in AGENTS.md.
- **R6 ✓** The README doesn't drift from the code: prose names no env var, and each command and flag under `## Use` is in the CLI's source or `bench/readme-cli`. Prose timings and source paths warn.

## Design (D)
- **D1 ✓** A UI repo may keep `DESIGN.md` in Google's format (templates/DESIGN.md). Its front matter parses, its `{ref}`s resolve and its `##` sections keep the spec's order, so agents and figma-cdp read one coherent source.

## Live runs (L)
- **L1** Before a live run, state what it will cost in tokens, turns and wall time. Costs are never in dollars.
- **L2** Run only the tasks a change touches, at 2 reps. Add a third only when the two disagree. Refreshing a baseline takes 3.
- **L3** Spend live runs sparingly. Read the transcripts you already have first, batch fixes into one run, and give routing-only changes a single smoke rep.
- **L4** After 5 runs in a row with no keep, stop or change approach.
- **L5** Before a run, predict each metric's verdict and name the reading that would prove the change wrong. When a verdict surprises you, check the bench before the code: its noise, its baseline, its commit.
- **L6** Run only the tasks `fium affects <base>..HEAD` names. It reads `bench/affects.json` (`{"rules": [{"files": [globs], "tasks": [...] | "*" | "none"}]}`, first match wins). A changed file no rule matches means every task, unless it is inert.

## Cost (K)
A change is done when the user has seen what it did to each of the project's own metrics and says it can merge. `fium done` measures them; something that broke or crossed a limit blocks it.
- **K1** Commit before you measure, so every experiment can be reverted.
- **K2** A bench writes `{"metrics": {name: {"dir": "lower"|"higher", "kind", "samples": [...]}}, "limits": {name: line}}`.
  - Exact metrics are judged on any move. Time and tokens are noisy by default. Set `"noisy": true` on anything else that varies between identical runs, such as an agent's turns or a scorer's output.
  - Noisy metrics are judged on the bootstrap range of the median ratio against 1 ± noise. Paired reps are judged on their rep-by-rep ratios. Noise comes from `bench/noise.json` (`{"rel": {metric: fraction}, "abs": {metric: amount}}`), written by `fium noise <aa-base> <aa-run>`: the farthest the A/A's range strays from 1, rounded up to a percent and at least 10%, the default; a move no bigger than `abs` is same.
  - A `limit` kind is judged only against its limit.
  - A run carries the `"commit"` it measured (`git rev-parse HEAD`) and `"dirty"`: whether `git status --porcelain` printed anything.
  - Runs live in `~/.fium/runs/<repo>/`, not in the repo.
- **K3** A worse, missing, limit or stale verdict blocks the change. A run is stale when its tree was dirty or its commit isn't HEAD. It is `carried`, and its numbers stand, when everything changed since matches an inert glob: the defaults plus any in `bench/inert` (one per line; a `!defaults` line drops the defaults; `bench/inert` itself is always inert). The defaults are the human docs, `test/`, `tests/`, noise and baseline files. Agent-facing docs such as SKILL.md and `references/` are never inert by default, since they change what a run measures. An unstamped run is flagged, not blocked. Inconclusive also blocks: its median is outside the noise band, but the range is too wide to call. Rerun it with more reps. With fewer than 5 reps on a side, a noisy metric is judged on its median against the band. The verdict is marked low-confidence (`low_n`, printed with a `?`), and a worse median still blocks.
- **K4 ✓** The user decides when a change is done. `fium done` measures every How we know row where the change left the base branch and now, and prints each number with its difference and percent; a row it can't run still shows, marked by hand. Each number is held to its cap (K6). The plan predicts the numbers it moves (W1), so the result has something to meet. The decision is the user's word in the conversation, never a record in commits or files. A project with goals says in AGENTS.md that a change is done when `fium done` says so.
- **K5** When the score is equal, less code wins (`git diff --shortstat`). Refresh the baseline only in its own commit. Unit tests assert what an action costs (queries, writes, calls) with the bench's fakes, so a cost regression fails the fast suite.
- **K6** The user chooses how firm each cap is, in one `Caps:` line under GOALS.md's How we know, like chmod: a digit per kind of number, `q` quality, `k` tokens, `n` counts and loc, `b` bytes, `t` time. `3` hard: the change isn't done until the number is the same or better, or the user agrees it can't get there without lowering quality. `2` semi-hard, the default: growth within its margin (`2:5` for 5%; none unless written) passes, and past it the user chooses to let it pass or have it simplified. `1` semi-hard with a 10% margin unless written (`1:25`). `0` soft: shown, no limit. `glob=digit` lines up one metric against its kind, and the last match wins: `Caps: q3 k2 n2 b1 t1 t.js*=2`. A line in a set number (Cloudflare's free tier) stays a `limit` in the baseline. `Topes:` is the same line. Only the user writes it, and only the user changes what a level means; test/test_done.py pins each one.

## Work (W)
How a change goes from an idea to done.
- **W1** Read the repo, then reply once: the plan (`R1…Rn`, each a result and the test that shows it, what's out, the numbers it moves) and at most three questions, each with a default. Numbers, not adjectives. The user's yes takes the defaults and freezes the plan (K4).
- **W2 ✓** Test first: each R's test names it and fails before the code; a fix starts with one that fails on the bug. Never edit an expectation to fit the code. Name a test for what the user sees; its assert message says why.
- **W3** One goal, about 100 lines besides tests; "for now" is another change. Done is every R green and one real run, checked against what the user first asked; until it does that, keep working without asking. A problem the change caused is never deferred.
- **W4** Tell the user things in their words: a goal by its name, a rule by what it says, each number with what it measures and its before → after. Never a goal's number, a rule's id or a cap's digit.

## Learning (S)
How a project learns from its own sessions, taken from figma-cdp's sleep loop.
- **S1** Learn from what agents actually did, not from what the docs imagine they do. Periodically read past transcripts for failed calls, retries, stalls, heavy reads and the user's corrections, and weight the corrections highest. Fix the top few, plus one or two rare ones.
- **S2** Every fix lands as a check that would fail without it: a test, an error text the code must print, or a rule a doc must keep. That way a later trim or rewrite can't silently forget it.
- **S3** Put the fix where the agent is when it fails. An error message that names the fix beats a line in a doc. An error or empty state a user sees says what happened and what to do next. When a failure comes back after its fix, move the fix closer to that point.
- **S4** A lesson says what to do, never only "X doesn't work". Drop hints and lessons that never fire. Environment trouble (Mac sleep, lock, permissions) belongs to the harness, not a project lesson.

## Commits (C)
- **C1** Commit messages say what landed, in the repo's own style: read its recent `git log` and match how subjects are phrased and how long bodies run. They carry no attribution lines.
- **C2** Push only with the user's OK.
