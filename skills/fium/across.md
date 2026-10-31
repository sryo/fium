# Across repos

One change, or one goal, that spans several repos under `~/Documents`. You manage. One session per repo does the work. Cite rule ids as in SKILL.md.

## 1. Research and audit (read-only)
- Run `fium status` and `fium check --all ~/Documents`. A repo's base is the branch its main checkout is on, which isn't always `main`. Cut every branch from that base and merge back into it.
- Fan out one agent per outside project and one per group of local repos. Give each a word cap, ask for file:line evidence, and have it mark every claim as either read in the source or inferred.

## 2. Plan outside the repos
- Write `~/.fium/campaigns/<name>.md` with one row per change: the repo, the change, and the failing test that proves it. No plan file goes in any repo.
- Within a repo, the failing tests are the spec. Write a spec only for a contract between repos, meaning an interface, its old and new behaviour, and the order changes land in. That contract also lives in the note.
- List the decisions only the user can make: deletions, API shape, memory edits, prices (K4). Ask them before the work reaches each one.

## 3. One session per repo
- Each session gets a brief with the goal, the files it owns, and what done means: the `## Test` command passes at a named commit. It cuts its own branch from the base. Never put two sessions on one repo at once.
- Sessions stage the paths they mean to commit, never `git add -A`. They commit with no attribution (C1), and they never push or merge.
- Keep `~/.fium/campaigns/<name>.json` up to date as `{"repos": {repo: [branch, ...]}}`.

## 4. Impact, before any merge
- Ask each session what its change breaks in other repos, then check the answer yourself. `fium grep <name>` searches every repo at its base. A worktree cut from the wrong base is how a caller gets missed.
- For a breaking change, test each caller's branch against the unmerged producer, for example by pointing the caller at the producer's worktree. Prefer expand, then contract: add the new name beside the old one, move the callers over, then remove the old one. If you skip the old name, land the producer and all its callers together.

## 5. Land
- Run `fium status --campaign <name>`. It reruns every branch's `## Test` command at the branch tip, so you don't have to trust a session's own report.
- Merge only after the user says yes (C2 covers the push). Run the tests on the merged base, and undo that merge if they fail.

## 6. Audit after merging
- Run `fium check --all`. For each name the change removed, run `fium grep <name>`.
- Run each repo's real entry point once (a CLI, a server, a headless agent run), because unit tests miss wiring.
- Re-read every README the change touched (R, R6). Keep each one short: say what it is, how to install it, the few commands people type, and its gaps.

## 7. Tidy
- `fium status --campaign <name>` prints the cleanup commands for the campaign's merged branches. Run them, then delete the campaign files and archive the sessions. Leave alone any branch the campaign didn't make.
