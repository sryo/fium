# fium

## Layout
- `RULES.md`: the rules
- `GOALS.md`: what fium is for
- `README.md`: install, use
- `AGENTS.md`: build, test
- `SKILL.md`: the skill
- `across.md`: the skill's /fium across
- `fium`: CLI entry
- `check.py`: check
- `compare.py`: compare, noise, scope
- `repos.py`: survey, status, grep, new
- `sleep.py`: sleep
- `templates/`: what new copies
- `bench/`: fium's bench
- `test/`: a file per module
- `LICENSE`: also new's

## Test
```bash
python3 -m unittest discover -s test
./fium check .
```

## Bench
fium is priced like any other project (RULES.md K). Commit first, then:
```bash
./fium compare $(bench/run.py --paired) --since <baseline commit>
```
Growth in read_bytes or loc needs a `Price:` trailer (K4).

A rule `fium check` can verify gets a ✓ in RULES.md and a test in test/test_check.py. Write the test first.
