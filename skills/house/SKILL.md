---
name: house
description: How the user wants every project built, measured and improved. Use when they want to start a new project ("I want to make something that does X"), bring an existing project in line, add benchmarks or cost pricing to one, write or fix a README/GOALS.md/AGENTS.md, or judge whether a change made anything cost more (tokens, calls, time, bytes, LOC).
---

The rules are in `~/Documents/house/RULES.md`. Read them first and cite rule ids (P4, R2, K4…). The aim (P) is simple, natural ways of doing things that are cheap on resources and reasonably fast, and that never intrude on the user.

## Start a new project
1. Ask only what you can't infer: who it's for, the job it does, and what it has to beat. Name it in plain lowercase.
2. `mkdir ~/Documents/<name> && cd $_ && git init`, then copy `~/Documents/house/templates/*` and replace NAME. Run `ln -s AGENTS.md CLAUDE.md`.
3. Write GOALS.md first:
   - purpose
   - never traded
   - goals in priority order
   - How we know, with a metric and a command for each goal
   - non-goals

   Then the README: why you'd want it and how you use it (R).
4. Before the first feature, set up `bench/` with a baseline in the run format (K2), so every later change gets priced.
5. Run `~/Documents/house/house check .` until it's clean. Commit with no attribution lines (C1).

## Bring an existing project in
1. Run `house check <repo>` and fix the errors one commit at a time. These are moves and docs only, with no behaviour changes:
   - CLAUDE.md → symlink
   - write GOALS.md from what AGENTS.md and the code already say
   - trim the README to why and how
2. If it has a bench, make it write the run format (K2) and gate it with `house price compare`. If it has none, add the cheapest one that measures its top goal.
3. Leave renames that would break suites (tests/ → test/) for the user to decide.

## Judge a change
1. Run the bench, then `house price compare bench/baseline.json <run> [--noise bench/noise.json] [--since main]`.
2. If the verdict is better or same, land it. If it's inconclusive, rerun with more reps. If it's worse, try three cheaper ways. If one is still worse, propose a `Price:` trailer with the numbers and ask the user (K4). Never cross a limit.
3. Before a live run, state its token cost and how many reps you'll buy (L1, L2).
