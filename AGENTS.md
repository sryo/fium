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
- `compare.py`: compare, noise, affects
- `done.py`: done
- `repos.py`: survey, status, grep, new
- `learn.py`: learn
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
fium is measured like any other project (RULES.md K4):
```bash
./fium done
```

A rule `fium check` can verify gets a ✓ in RULES.md and a test in test/test_check.py. Write the test first.
