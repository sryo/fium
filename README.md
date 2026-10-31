# house

house is the one set of rules every sryo project follows, with templates for new projects and a checker that tells you where a repo drifts.

## Install
```bash
git clone https://github.com/sryo/house ~/Documents/house && ln -s ~/Documents/house/skills/house ~/.claude/skills/house
```

## Use
```bash
~/Documents/house/house check ~/Documents/perch
~/Documents/house/house check --all ~/Documents
```

Each finding names a rule in RULES.md and the fix.
