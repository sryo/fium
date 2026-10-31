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
./fium price compare bench/baseline.json $(bench/run.py)
```
A change that rewords rules or grows the checker must not raise read_bytes or loc without a `Price:` trailer.

A rule `fium check` can verify gets a ✓ in RULES.md and a test in test/test_check.py. Write the test first.
