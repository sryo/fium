# fium: goals

## What fium is for
One way of doing things across every sryo project, all serving the same aim (RULES.md P): natural, simple, cheap on resources, reasonably fast, never intruding on the user. Agents and the user find the same files, goals format and loop everywhere.

## Never traded
- A rule never changes a project's behaviour. Migrations are file and doc moves only.
- Checks report; they never rewrite a repo.

## Goals, in priority order
1. **Every rule is citable.** Each has an id and one line saying why.
2. **Checkable rules are checked.** If a script can verify it, `fium check` does.
3. **Few rules.** A rule earns its place by preventing a real, repeated mess.

## How we know
| Goal | Metric | Where |
|---|---|---|
| 1 | every rule has an id | `RULES.md` |
| 2 | ✓ rules each have a test | `test/test_check.py` |
| 3 | rule count; repos passing | `./fium check --all ~/Documents` |

## Non-goals
- Enforcing style inside code. Linters do that per language.
- Auto-fixing repos.
