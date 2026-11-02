# fium

fium gives you one way to lay out, measure and improve your projects: rules your agents can cite, templates for new repos, and a checker that tells you where a repo drifts.

## Install
```bash
git clone https://github.com/sryo/fium ~/Documents/fium
mkdir -p ~/.claude/skills && ln -sfn ~/Documents/fium ~/.claude/skills/fium
```

## Use
Ask your agent in plain words, and the fium skill picks the step:
- "Start a project that does X": it makes the repo from the templates and writes the goals first.
- "Bring perch in line": it fixes what the checker finds, one rule at a time.
- "Is this done?": `fium done` measures every metric in the project's goals where the change started and now, and asks you only when a cap says so.
- `/fium across <goal>`: one goal across several repos. It researches, plans, runs one session per repo, and merges after your yes.

To see where your repos stand yourself:
```bash
~/Documents/fium/fium check --all ~/Documents
~/Documents/fium/fium status
```
