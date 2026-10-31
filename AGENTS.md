# house

The rules every project follows (RULES.md), templates for new ones (templates/), a checker (`house`) and the skill that teaches agents both (skills/house/). GOALS.md says what house is for.

## Test
```bash
python3 -m unittest discover -s test
./house check .
```

A rule `house check` can verify gets a ✓ in RULES.md and a test in test/test_check.py. Write the test first.
