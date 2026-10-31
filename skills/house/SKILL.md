---
name: house
description: House rules for every sryo project — file layout (AGENTS.md + CLAUDE.md symlink, GOALS.md, README, test/, bench/), goals with metrics, README voice, how live eval loops are priced, keep/revert, and how lessons get mined. Use when creating a new project, editing a README/GOALS/AGENTS file, setting up a bench or self-improvement loop, or reviewing a repo against the rules.
---

Read `~/Documents/house/RULES.md` and cite rule ids (F2, L3, K3...) in reviews and plans.

- **New project:** copy `~/Documents/house/templates/` (replace NAME), `ln -s AGENTS.md CLAUDE.md`, then `house check`.
- **Editing a project:** run `~/Documents/house/house check <repo>` before committing; fix errors, mention warnings.
- **Survey:** `house check --all ~/Documents`.
- **Loops:** before any live run, state expected tokens (L2) and the reps you'll buy (L3).
