# fium: goals

## What fium is for
Start something and finish it. Before work starts you agree what done means, as checks or numbers. An agent then keeps going until each is met, the budget runs out, or it needs an answer only you can give, never because it feels done. Every project has the same files, goals format and numbers, so any agent picks up where another stopped, shows what it did to the numbers, and turns each failure into a check that stays. All of it serves one aim (RULES.md P): natural, simple, cheap on resources, reasonably fast, never intruding on the user.

## Never traded
- A rule never changes a project's behaviour. Migrations are file and doc moves only.
- Checks report; they never rewrite a repo.
- The user never decodes. Whatever an agent tells them names things in plain words: goals by name, rules by what they say, each number with what it measures.
- Done is what the user asked, checked for real. Until then the agent keeps working, without asking.

## Goals, in priority order
1. **Every rule is citable.** Each has an id and one line saying why.
2. **Checkable rules are checked.** If a script can verify it, `fium check` does.
3. **Few rules.** A rule earns its place by preventing a real, repeated mess.
4. **Cheap to read and run.** Agents read the rules every session, and the checker runs on every repo.

## How we know
| Goal | Metric | Where | Run |
|---|---|---|---|
| 1 | rules without an id (limit 0) | `bench/run.py` unnamed_rules | `bench/run.py` |
| 2 | ✓ rules without a test (limit 0) | `bench/run.py` untested_checks | `bench/run.py` |
| 2 | replies the turn-end hook sends back wrongly, or lets through, on sessions labelled by hand (limit 0); its time on the longest | `bench/hook.py` wrong_blocks, missed_blocks, hook_ms | `bench/hook.py` |
| 3 | rule count | `bench/run.py` rules | `bench/run.py` |
| 3 | repos with errors | `./fium check --all ~/Documents` | `./fium check --all ~/Documents --json \| python3 -c "import json,sys; print(sum(any(f['level'] == 'error' for f in fs) for fs in json.load(sys.stdin).values()))"` |
| 4 | bytes an agent reads; checker LOC; check, check --all and compare time | `bench/run.py` read_bytes, loc, check_ms, check_all_ms, compare_ms | `bench/run.py` |

## Non-goals
- Enforcing style inside code. Linters do that per language.
- Auto-fixing repos.
