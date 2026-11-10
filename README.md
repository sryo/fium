<h1>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/logo/fium-dark.svg">
    <img alt="fium" src="docs/logo/fium-light.svg" width="200">
  </picture>
</h1>

fium gives you one way to lay out, measure and improve your projects: rules your agents can cite, templates for new repos, and a checker that tells you where a repo drifts.

## Install
```bash
curl -fsSL https://raw.githubusercontent.com/sryo/fium/main/install.sh | bash
```

## Use
Ask your agent in plain words, and the fium skill picks the step:
- "Start a project that does X": it makes the repo from the templates and writes the goals first.
- "Bring perch in line": it fixes what the checker finds, one rule at a time.
- "Is this done?": `fium done` measures every metric in the project's goals where the change started and now, and asks you only when a number grows more than you allow.
- "Improve perch overnight": it tries one idea at a time in a worktree, keeps what makes the numbers better, reverts the rest, and logs why. Cuts anywhere count. You merge the keeps.
- "Learn from this week's sessions": `fium learn` finds where agents failed, retried or were corrected, ranks it, and keeps each fix as a check.
- `/fium across <goal>`: one goal across several repos. It researches, plans, runs one session per repo, and merges after your yes.

To see where your repos stand yourself:
```bash
fium check --all ~/Documents
fium status
```
