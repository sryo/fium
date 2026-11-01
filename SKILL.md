---
name: fium
description: How the user wants every project built, measured and improved. Use when they want to start a new project ("I want to make something that does X"), bring an existing project in line, add benchmarks or cost pricing to one, write or fix a README/GOALS.md/AGENTS.md, judge whether a change made anything cost more (tokens, calls, time, bytes, LOC), or run one goal across several repos (/fium across).
---

The rules are in `~/Documents/fium/RULES.md`. Read them first and cite rule ids (P1, R2, K4…). The aim (P) is simple, natural ways of doing things that are cheap on resources and reasonably fast, and that never intrude on the user.

## Start a new project
1. Ask only what you can't infer: who it's for, the job it does, and what it has to beat. Name it in plain lowercase.
2. `cd ~/Documents && fium/fium new <name>` makes the repo from the templates.
3. Write GOALS.md first:
   - purpose
   - never traded
   - goals in priority order
   - How we know, with a metric and a command for each goal
   - non-goals

   Then the README: why you'd want it and how you use it (R).
4. Before the first feature, set up `bench/` with a baseline in the run format (K2), so every later change gets priced.
5. A UI repo can add DESIGN.md (templates/DESIGN.md, D1); figma-cdp reads it as the source.
6. Run `~/Documents/fium/fium check .` until it's clean. Commit with no attribution lines (C1).

## Bring an existing project in
1. Run `fium check <repo>` and fix the errors one commit at a time. These are moves and docs only, with no behaviour changes:
   - CLAUDE.md → symlink
   - write GOALS.md from what AGENTS.md and the code already say
   - trim the README to why and how
2. If it has a bench, make it write the run format (K2) and gate it with `fium compare`. If it has none, add the cheapest one that measures its top goal.
3. Leave renames that would break suites (tests/ → test/) for the user to decide.

## Build a change (W)
1. Read GOALS.md and the code it touches, then reply once with the plan and the questions (W1).
2. On yes: tests first and red, code to green, one real run, `fium compare`.
3. Report each R, the run and the numbers. Push only on the user's OK.

## Judge a change
1. Quote each proposal's price before building (K4).
2. Run the bench, then `fium compare bench/baseline.json <run> [--noise bench/noise.json] [--since main]`. The base can be a commit instead of a file: compare keeps every clean run it judges in `~/.fium/runs`.
3. Within its quote, land it with its `Price:` trailers. Inconclusive (exit 3): rerun with more reps. Over: try cheaper ways, then show the user the gap. Never cross a limit.
4. Before a live run, state its token cost and how many reps you'll buy (L1, L2), predict each verdict (L5), and run only the tasks `fium scope <base>..HEAD` names (L6).
5. A stale verdict means the run measured another commit or a dirty tree. Commit, then rerun on HEAD (K1, K3).

## Learn from past sessions (S)
After a working day or a live run, mine what agents actually did. `fium sleep mine`, then `digest`, reads the project's `~/.claude/projects` transcripts; `bench/sleep.json` adds sources, hint tables and gates (`fium sleep --help`). `learn` keeps each fix as a lesson that `replay` checks. Fix the top clusters test-first, so that each fix lands as a check (S2), placed where the failure happens (S3).

## Across repos
For one goal across several repos (`/fium across <goal>`), read `across.md` beside this file and follow it. Even in one repo, `fium grep <name>` finds a name's users in every repo before you rename or remove it, and `fium status` shows each repo's branches.

To improve fium itself, propose rule or template changes from `fium survey` to the user.
