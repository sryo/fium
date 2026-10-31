# fium

fium is the one set of rules every sryo project follows, with templates for new projects and a checker that tells you where a repo drifts.

## Install
```bash
git clone https://github.com/sryo/fium ~/Documents/fium && ln -s ~/Documents/fium/skills/fium ~/.claude/skills/fium
```

## Use
```bash
~/Documents/fium/fium check ~/Documents/perch
~/Documents/fium/fium check --all ~/Documents
```

Each finding names a rule in RULES.md and the fix.
