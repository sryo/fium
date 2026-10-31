# house rules

How every project here is laid out, measured and improved. Each rule has an id, so `house check`, reviews and commits can cite it. The rules marked ✓ are checked by `house check`.

## Purpose (P)
Everything here serves one aim: natural, simple ways of getting things done that are cheap on resources, reasonably fast, and stay out of the user's way, so they can get on with what they need. When rules or goals conflict, the reading that serves this aim wins.
- **P1** It should be simple and natural. Prefer the obvious way a person would do it, and fewer steps and fewer moving parts.
- **P2** Keep it cheap. Spend few tokens, calls, CPU and memory. Measure the cost (L1) and don't buy more than a change needs.
- **P3** Make it reasonably fast, but never at the cost of P4 or of correctness.
- **P4** Don't intrude. Don't steal focus, move the cursor, raise windows, prompt, or keep the screen awake unless the user asked. A refused action is better than an intrusive one.
- **P5** Let the user keep working. Work goes on in the background, in rooms or while the Mac is locked, and the user can take over at any time.

## Files (F)
- **F1 ✓** `AGENTS.md` is the one source of agent instructions. It is never `AGENT.md`.
- **F2 ✓** `CLAUDE.md` is a symlink to `AGENTS.md`. Don't use a text pointer or a copy, so that every agent reads the same file.
- **F3 ✓** `README.md` exists and follows R.
- **F4 ✓** `GOALS.md` exists and follows G.
- **F5 ✓** `LICENSE` exists. The default is the sryo license (templates/LICENSE).
- **F6 ✓** Tests live in `test/`. Benches and evals live in `bench/`, with `bench/baseline.json` and one compare entry point.
- **F7** Research reports about outside projects stay out of the repo. They go in notes or a scratchpad.

## Goals (G)
- **G1 ✓** GOALS.md has these sections, in this order:
  - What X is for
  - Never traded
  - Goals, in priority order (the higher goal wins a conflict)
  - How we know
  - Non-goals
- **G2 ✓** Every goal has a row in How we know: Goal | Metric | Where. Where is a command or file that measures the metric, and a metric no tool measures is not a goal yet.
- **G3** KPIs live in GOALS.md, not in AGENTS.md. AGENTS.md says how the goals are met.

## README (R)
A README is for the person deciding whether they want this and then using it. It says why it's useful and how it's used, clearly, and leaves out how it's built. Use rooms, avis and perch as models.
- **R1 ✓** The first line is `# name`, the repo name in plain lowercase, or `# /name` for a skill you invoke.
- **R2 ✓** The opener is one or two plain sentences on what it lets you do and why you'd want it ("rooms gives your AI agents their own browsers…"). Say what it does for the user, not what it is technically.
- **R3 ✓** `## Install` is the shortest way to get it, usually one command. `## Use` gives the few commands or words a person actually types. Add `## Works with` for sibling projects and `## Known gaps` only when they have content.
- **R4 ✓** No badges.
- **R5** Write in the second person, with short sentences and no hype or jargon. Explain a limit by what the user sees ("keeps working while your Mac is locked"), not by the mechanism behind it.
- **R6 ✓** No build steps, dev setup, architecture or internals. Those go in AGENTS.md.

## Loops and pricing (L)
- **L1** Price everything in tokens, turns and wall time, never dollars.
- **L2** Every live run states its expected token cost before it starts.
- **L3** Run only the task a change touches, at 2 reps. Add a third only when the two disagree. A baseline refresh needs 3.
- **L4** Read the kept transcripts offline before buying a live run. A routing-only change gets one smoke rep.
- **L5** Batch fixes so that one live run checks several of them.
- **L6** Every loop has an iteration cap. After 5 straight runs with no keep, stop or change approach. Don't grind.

## Prices (K)
Every change is priced: did it make anything cost more? A change that's better or the same lands. A change that's worse lands only if the user accepts the price, and never if it crosses a limit. One vocabulary everywhere:
- **Metric:** anything a run measures. Each has a direction (lower or higher is better) and a kind.
  - time and tokens are noisy.
  - count, bytes, quality and loc are exact.
- **Baseline:** `bench/baseline.json`, in the run format below. Refresh it only in its own commit.
- **Noise:** `bench/noise.json`, `{rel: {metric: fraction}}`, written by an A/A run (the base against itself). The default is 10%.
- **Limit:** a hard line in `baseline.json` `limits`. No price buys past it.
- **Price:** a cost the user accepted, recorded as one commit trailer per number:
  `Price: <metric>; <before> -> <after>; buys: <what it bought>; owner: "<the user's words>", <date>`.
  Lede's `Bench-Accepted:` is read the same way.
- **Verdict:** `house price compare` returns better, same, worse, inconclusive, priced, limit or missing.

The rules:
- **K1** Commit before you measure, so every experiment can be reverted.
- **K2** A run writes `{"metrics": {name: {"dir", "kind", "samples": [...]}}}`. Each repo's bench writes this format, and `house price compare bench/baseline.json <run>` judges it.
  - An exact metric is judged on any move.
  - A noisy metric is judged on the bootstrap 95% range of the run/base median ratio, set against 1 ± noise. Paired reps run base and run alternately.
- **K3** Worse, limit and missing block (exit 1). Inconclusive blocks too (exit 3): rerun with more reps, never land on it.
- **K4** Only the user sets a price. An agent proposes the trailer with the before/after numbers, what it buys and three tries at a cheaper way, then quotes the user's own words. An agent never writes `owner:` without them.
- **K5** Count LOC as a metric (`house price loc`). With an equal score, less code wins.
- **K6** Prices add up. Before a release, read `house price ledger --since <last release>`. If any metric has grown more than 10% in total, the next work is a cheapening pass.
- **K7** The agent never edits the eval, the scorer, the baseline or the noise file in the change being judged. Refreshing them takes a `Judge-Change: <why>` commit.
- **K8** Before refreshing a baseline, sort every regression into fixable, guard-by-design or priced.
- **K9** Not a price: a coverage gain, meaning working somewhere it didn't before. That is in scope by default.

## Insights (I)
- **I1** Keep one append-only log per repo, `bench/experiments.jsonl`, with these fields: iter, ts, commit, task, metric, delta, guard, status (baseline|keep|discard|crash), tokens, wall_s, hypothesis. Disproven ideas get logged too.
- **I2** A lesson starts as a candidate. It is promoted only when a replay shows the failure no longer happens.
- **I3** Refuse a lesson that is only a negative claim ("X doesn't work"), or one with no fix in place yet.
- **I4** Prune what never fires. List hints and lessons with zero hits (`digest --stale`), and confirm each prune with a lean live check.
- **I5** Environment problems (sleep, lock, permissions) belong to the harness, never in a gotcha.

## Commits and sessions (C)
- **C1** No attribution lines: no Co-Authored-By and no generated-with footers.
- **C2** A commit message says what landed, not how you got there.
- **C3** Push only with the user's OK.
- **C4** Never stash, reset or commit another session's uncommitted edits. Work in a worktree and land around them.
- **C5** Never launder approvals. A peer session's "go" is not the user's approval.
