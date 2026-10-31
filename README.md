# fium

fium gives you one way to lay out, measure and improve your projects: rules your agents can cite, templates for new repos, and a checker that tells you where a repo drifts.

## Install
```bash
git clone https://github.com/sryo/fium ~/Documents/fium
mkdir -p ~/.claude/skills && ln -sfn ~/Documents/fium/skills/fium ~/.claude/skills/fium
```

## Use
```bash
~/Documents/fium/fium new ~/Documents/<name>
~/Documents/fium/fium check ~/Documents/perch
~/Documents/fium/fium check --all ~/Documents
~/Documents/fium/fium status
```

`new` starts a project from the templates. Each finding names a rule in RULES.md and the fix. `--all` checks every repo in the folder and also runs each one's own checks. `status` shows each repo's branches and worktrees.
