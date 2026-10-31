# fium rules

How every project here is laid out, measured and improved. Each rule has an id for reviews and commits to cite. `fium check` checks the rules marked ✓.

**P1 The aim.** Natural, simple ways of doing things that are cheap on resources, reasonably fast, and never get in the user's way. When two rules conflict, the reading that serves this aim wins.

## Files (F)
- **F1 ✓** `AGENTS.md` holds the agent instructions: how the project is built and tested. It is never named `AGENT.md`.
- **F2 ✓** `CLAUDE.md` is a symlink to `AGENTS.md`.
- **F3 ✓** `README.md`, following R.
- **F4 ✓** `GOALS.md`, following G.
- **F5 ✓** `LICENSE`. The default is the sryo license (templates/LICENSE).
- **F6 ✓** Agent docs (AGENTS.md, SKILL.md) have no `@` imports. When an import stops resolving, its text drops silently.
- **F7 ✓** AGENTS.md has a `## Test` section with the command that runs the tests.

## Memory (M)
- **M1 ✓** Each memory file (`~/.claude/projects/<project>/memory/`) opens with `name` and `description` frontmatter, so an agent loads those lines and reads a body only when it needs it.

## Goals (G)
- **G1 ✓** GOALS.md has these sections:
  - What X is for
  - Never traded
  - Goals, in priority order (the higher goal wins a conflict)
  - How we know
  - Non-goals
- **G2 ✓** Every goal has a How we know row: Goal | Metric | Where. Where is the command, test or file that measures it, or "manual" when nothing can measure it yet.

## README (R)
A README is for someone deciding whether they want this, and then using it. It says why it's useful and how to use it, in plain words. Use rooms, avis and perch as models.
- **R1 ✓** The first line is `# name`, the repo name in lowercase. A skill you invoke may use `# /name`.
- **R2 ✓** The opener is one or two sentences on what it lets you do and why you'd want it. Use second person, short sentences, no hype or jargon. Describe limits by what the user sees, not by how it works inside.
- **R3 ✓** Then `## Install`, the shortest way to get it, and `## Use`, the few things a person actually types. Add `## Works with` and `## Known gaps` only when they have something to say.
- **R4 ✓** No badges.
- **R5 ✓** No build steps, dev setup or internals. Those belong in AGENTS.md.

## Live runs (L)
- **L1** Before a live run, state what it will cost in tokens, turns and wall time. Prices are never in dollars.
- **L2** Run only the tasks a change touches, at 2 reps. Add a third only when the two disagree. Refreshing a baseline takes 3.
- **L3** Spend live runs sparingly. Read the transcripts you already have first, batch fixes into one run, and give routing-only changes a single smoke rep.
- **L4** After 5 runs in a row with no keep, stop or change approach.
- **L5** Before a run, predict each metric's verdict and name the reading that would prove the change wrong. When a verdict surprises you, check the bench before the code: its noise, its baseline, its commit.
- **L6** Run only the tasks `fium scope <base>..HEAD` names. It reads `bench/affects.json` (`{"rules": [{"files": [globs], "tasks": [...] | "*" | "none"}]}`, first match wins). A changed file no rule matches means every task, unless it is inert.

## Prices (K)
A change lands only if it costs no more than before, unless the user accepts the price. A limit blocks it even then. `fium price compare bench/baseline.json <run>` makes the call.
- **K1** Commit before you measure, so every experiment can be reverted.
- **K2** A bench writes `{"metrics": {name: {"dir": "lower"|"higher", "kind", "samples": [...]}}, "limits": {name: line}}`.
  - Exact metrics are judged on any move. Time and tokens are noisy by default. Set `"noisy": true` on anything else that varies between identical runs, such as an agent's turns or a scorer's output.
  - Noisy metrics are judged on the bootstrap range of the median ratio against 1 ± noise. Paired reps are judged on their rep-by-rep ratios. Noise comes from `bench/noise.json` (`{"rel": {metric: fraction}, "abs": {metric: amount}}`), written by an A/A run, and defaults to 10%; a move no bigger than `abs` is same.
  - A `limit` kind is judged only against its limit.
  - A price covers an exact metric's growth up to what its trailers add up to.
  - A run carries the `"commit"` it measured (`git rev-parse HEAD`) and `"dirty"`: whether `git status --porcelain` printed anything.
- **K3** A worse, missing, limit or stale verdict blocks the change. A run is stale when its tree was dirty or its commit isn't HEAD. It is `carried`, and its numbers stand, when everything changed since matches an inert glob: the defaults plus any in `bench/inert` (one per line; a `!defaults` line drops the defaults; `bench/inert` itself is always inert). The defaults are the human docs, `test/`, `tests/`, noise and baseline files. Agent-facing docs such as SKILL.md and `references/` are never inert by default, since they change what a run measures. An unstamped run is flagged, not blocked. Inconclusive also blocks: its median is outside the noise band, but the range is too wide to call. Rerun it with more reps. With fewer than 5 reps on a side, a noisy metric is judged on its median against the band. The verdict is marked low-confidence (`low_n`, printed with a `?`), and a worse median still blocks.
- **K4** Only the user sets a price. The agent tries three cheaper ways first, then proposes one trailer per number: `Price: <metric>; <before> -> <after>; buys: <what>; tried: <what>; owner: "<the user's words>", <date>`. The agent never writes the owner's words itself.
- **K5** When the score is equal, less code wins (`git diff --shortstat`). Refresh the baseline only in its own commit.
- **K6** The user chooses how firm each cap is, in one `Caps:` line under GOALS.md's How we know. A digit per kind sets the default: `q` quality, `k` tokens, `n` counts and loc, `b` bytes, `t` time. `0` is only reported. `1` may grow by its slack (10%, or `1:25` for 25%), and that verdict is `grew`, which doesn't block. `2`, the default, needs a price. `3` never grows, not even with a price. `glob=digit` lines up one metric against its kind, and the last match wins: `Caps: q3 k2 n2 b1 t1 t.js*=2`. A line in a set number (Cloudflare's free tier) stays a `limit` in the baseline. `Topes:` is the same line. Only the user writes it.

## Learning (S)
How a project learns from its own sessions, taken from figma-cdp's sleep loop (figma-cdp `docs/sleep-loop.md`).
- **S1** Learn from what agents actually did, not from what the docs imagine they do. Periodically read past transcripts for failed calls, retries, stalls, heavy reads and the user's corrections, and weight the corrections highest. Fix the top few, plus one or two rare ones.
- **S2** Every fix lands as a check that would fail without it: a test, an error text the code must print, or a rule a doc must keep. That way a later trim or rewrite can't silently forget it.
- **S3** Put the fix where the agent is when it fails. An error message that names the fix beats a line in a doc. When a failure comes back after its fix, move the fix closer to that point.
- **S4** A lesson says what to do, never only "X doesn't work". Drop hints and lessons that never fire. Environment trouble (sleep, lock, permissions) belongs to the harness, not to a project lesson.

## Commits (C)
- **C1** Commit messages say what landed. They carry no attribution lines.
- **C2** Push only with the user's OK.
