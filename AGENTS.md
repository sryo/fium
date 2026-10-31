# fium

The rules every project follows (RULES.md), templates for new ones (templates/), a checker (`fium`) and the skill that teaches agents both (skills/fium/). GOALS.md says what fium is for.

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
