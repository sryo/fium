# house rules

How every project here is laid out, measured and improved. Each rule has an id for reviews and commits to cite. `house check` checks the rules marked ✓.

**P1 The aim.** Natural, simple ways of doing things that are cheap on resources, reasonably fast, and never get in the user's way. When two rules conflict, the reading that serves this aim wins.

## Files (F)
- **F1 ✓** `AGENTS.md` holds the agent instructions: how the project is built and tested. It is never named `AGENT.md`.
- **F2 ✓** `CLAUDE.md` is a symlink to `AGENTS.md`.
- **F3 ✓** `README.md`, following R.
- **F4 ✓** `GOALS.md`, following G.
- **F5 ✓** `LICENSE`. The default is the sryo license (templates/LICENSE).

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

## Prices (K)
A change lands only if it costs no more than before, unless the user accepts the price. A limit blocks it even then. `house price compare bench/baseline.json <run>` makes the call.
- **K1** Commit before you measure, so every experiment can be reverted.
- **K2** A bench writes `{"metrics": {name: {"dir": "lower"|"higher", "kind", "samples": [...]}}, "limits": {name: line}}`.
  - Exact metrics are judged on any move. Time and tokens are noisy by default. Set `"noisy": true` on anything else that varies between identical runs, such as an agent's turns or a scorer's output.
  - Noisy metrics are judged on the bootstrap range of the median ratio against 1 ± noise. Paired reps are judged on their rep-by-rep ratios. Noise comes from `bench/noise.json` (`{"rel": {metric: fraction}, "abs": {metric: amount}}`), written by an A/A run, and defaults to 10%; a move no bigger than `abs` is same.
  - A `limit` kind is judged only against its limit.
  - A price covers an exact metric's growth up to what its trailers add up to.
- **K3** A worse, missing or limit verdict blocks the change. Inconclusive also blocks: its median is outside the noise band, but the range is too wide to call. Rerun it with more reps. For agent evals at 2 reps, add a third rep once. If it's still inconclusive, show the user the numbers rather than buying more reps (L2).
- **K4** Only the user sets a price. The agent tries three cheaper ways first, then proposes one trailer per number: `Price: <metric>; <before> -> <after>; buys: <what>; tried: <what>; owner: "<the user's words>", <date>`. The agent never writes the owner's words itself.
- **K5** When the score is equal, less code wins (`git diff --shortstat`). Refresh the baseline only in its own commit.

## Learning (S)
How a project learns from its own sessions, taken from figma-cdp's sleep loop (figma-cdp `docs/sleep-loop.md`).
- **S1** Learn from what agents actually did, not from what the docs imagine they do. Periodically read past transcripts for failed calls, retries, stalls, heavy reads and the user's corrections, and weight the corrections highest. Fix the top few, plus one or two rare ones.
- **S2** Every fix lands as a check that would fail without it: a test, an error text the code must print, or a rule a doc must keep. That way a later trim or rewrite can't silently forget it.
- **S3** Put the fix where the agent is when it fails. An error message that names the fix beats a line in a doc. When a failure comes back after its fix, move the fix closer to that point.
- **S4** A lesson says what to do, never only "X doesn't work". Drop hints and lessons that never fire. Environment trouble (sleep, lock, permissions) belongs to the harness, not to a project lesson.

## Commits (C)
- **C1** Commit messages say what landed. They carry no attribution lines.
- **C2** Push only with the user's OK.
