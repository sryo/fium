---
name: fium
description: How the user wants every project built, measured and improved. Use when they want to start a new project ("I want to make something that does X"), bring an existing project in line, add benchmarks to one, write or fix a README/GOALS.md/AGENTS.md, decide whether a change is done from what it did to the project's own metrics (tokens, calls, time, bytes, LOC…), or run one goal across several repos (/fium across).
---

The rules are in `~/Documents/fium/RULES.md`. Read them first. Cite rule ids (P1, R2, K4…) in files and commits, never to the user (W4). The aim (P) is simple, natural ways of doing things that are cheap on resources and reasonably fast, and that never intrude on the user.

## Start a new project
1. Ask only what you can't infer: who it's for, the job it does, and what it has to beat. Name it in plain lowercase.
2. `cd ~/Documents && fium new <name>` makes the repo from the templates.
3. Write GOALS.md first:
   - purpose
   - never traded
   - goals in priority order
   - How we know, with a metric, where it's measured and what `fium done` runs for each goal
   - `Caps:`, which only the user sets (K6)
   - non-goals

   Then the README: why you'd want it and how you use it (R).
4. Before the first feature, set up `bench/` with a baseline in the run format (K2), so `fium done` can measure every later change.
5. A UI repo can add DESIGN.md (templates/DESIGN.md, D1); figma-cdp reads it as the source.
6. Run `fium check .` until it's clean. Commit with no attribution lines (C1).

## Bring an existing project in
1. Run `fium check <repo>` and fix the errors one commit at a time. These are moves and docs only, with no behaviour changes:
   - CLAUDE.md → symlink
   - write GOALS.md from what AGENTS.md and the code already say
   - trim the README to why and how
2. If it has a bench, make it write the run format (K2). If it has none, add the cheapest one that measures its top goal. Give GOALS.md's How we know a Run cell per row (G2), and say in AGENTS.md that a change is done when `fium done` says so (K4). `bench/` may hold `checks` (F8), `inert` (K3), `judge` (K5), `affects.json` (L6), `noise.json` (K2), `readme-cli` (R6) and `learn.json` (S).
3. Leave renames that would break suites (tests/ → test/) for the user to decide.

## Build a change (W)
1. Read GOALS.md and the code it touches, then reply once with the plan and the questions (W1).
2. On yes: `fium done --start` (the live rows' before), tests first and red, code to green, one real run, `fium done`.
3. Report each R, the run and the numbers in the user's words (W4). Push only on the user's OK.

## Judge a change
1. The plan predicts the numbers the change moves (W1).
2. Built, always judge it with `fium done`, not `fium compare`: every How we know row, measured where the change left the base branch and now. Add `--costly` for the agent evals only after stating their tokens and reps (L1, L2), predicting each verdict (L5) and running only the tasks `fium affects <base>..HEAD` names (L6).
3. Exit 1: not done. Fix what broke; a hard number that got worse needs simplifying until it's the same or better, and only if it can't get there without lowering quality, show the user why. Exit 3: an ask number got worse past its margin, so simplify it first, then show the user the numbers and ask whether it passes. "Couldn't measure" (a command failed at the base or both sides) keeps it open too: make it run clean, or the user says it needn't. Exit 0: it can merge. Never cross a limit. Write the answer nowhere (K4). Tell it under each goal's name, as `fium done` prints it (W4).
4. `fium compare <base-run> <run>` judges two runs directly. A stale verdict means the run measured another commit or a dirty tree (K1, K3).

## Loop
To improve a project's numbers unattended (try, measure, keep or revert, repeat), read `loop.md` beside this file and follow it.

## Learn from past sessions (S)
After a working day or a live run, mine what agents actually did. `fium learn mine`, then `digest`, reads the project's transcripts, plus what `learn.json` adds (`fium learn --help`). `keep` keeps each fix as a lesson `replay` checks; `check` gates a fix. Fix the top clusters test-first, so each fix lands as a check (S2), placed where the failure happens (S3).

## Across repos
For one goal across several repos (`/fium across <goal>`), read `across.md` beside this file and follow it. Even in one repo, `fium grep <name>` finds a name's users in every repo before you rename or remove it, and `fium status` shows each repo's branches.

To improve fium itself, propose rule or template changes from `fium survey` to the user.
