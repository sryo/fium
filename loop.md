# Loop

Improve one project's numbers unattended: try an idea, measure it, keep or revert it, log why, and go again until a stop. `fium try` judges and logs each attempt; you make the changes and the resets. Cite rule ids as in SKILL.md.

## 1. One approval up front
Reply once (W1) with:
- the project and the files the loop may edit
- the number an addition must make better (`--target`)
- what it tries first
- the budget in tokens, wall time and attempts. The default is 3M tokens and 2 hours of live runs per project; free rows are unlimited.

The user's yes covers every run inside that budget, so each run needn't state its cost again (L1).

## 2. Set up
- Work in a worktree beside the repo, on its own branch from the base: `git worktree add ../<repo>-loop-<date> -b loop/<date>`. Never loop in the user's checkout, tabs or foreground. A live eval that drives a browser runs in a perch room, one loop per eval file.
- `bench/judge` must name everything that judges: scorers, the eval runner, fixtures, and any config that acts in the world (sends, submits, buys). Add what's missing on the base branch first, never inside the loop.
- Run the bench twice at HEAD. `fium compare` must say only same. If it doesn't, fix the harness or measure noise (`fium noise`) before any attempt.
- `fium try baseline --record keep`.

## 3. Each attempt
1. `fium try`: read the past attempts, and why the ones that touched the same files were dropped.
2. Make one change, predict its verdict (L5), commit.
3. `fium try "<idea>"`, with `--target <metric>` when it adds. Add `--costly` only for the tasks `fium affects` names (L6).
4. `confirm`: `fium try --confirm --costly`.
5. `retest`: run it once more with more reps. Anything but `keep`: `git reset --hard` to the last keep.

## 4. What to try
- Cuts anywhere: a section of an always-loaded doc, a hint or lesson `fium learn digest --stale` says never fires, dead code, a dependency, a config key. A cut nothing measures is parked; measure it or leave it.
- Additions only with a target number.
- A near miss from the log, never an idea the log dropped for the same files without a new reason.

## 5. Stop
- 5 attempts in a row with no keep (`fium try` says so), the budget spent, or a crash two fixes didn't cure.
- Never inside the loop: write lessons, change `bench/judge`, refresh a baseline, push or merge.

## 6. Report
`fium try`'s list and the branch name. The keeps wait on `loop/<date>` for `fium done` against the base and the user's word (K4). Say it in plain words (W4).
