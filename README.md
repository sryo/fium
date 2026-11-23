<h1>
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/logo/fium-wide-dark.svg">
    <img alt="fium" src="docs/logo/fium-wide-light.svg" width="100%">
  </picture>
</h1>

Start something and see it finished. You agree what done means up front; fium keeps your agents working until it's met, shows what each change did to the numbers, and turns each mistake into a check that stays.

| Without fium | With fium |
|---|---|
| Each chat starts over | Agents find the same files and goals in every repo |
| Done is a feeling | Done is when the numbers say so |
| The same mistake comes back | Each mistake becomes a check |
| You improve things by hand | It tries ideas overnight and keeps what measures better |

## Install
```bash
curl -fsSL https://raw.githubusercontent.com/sryo/fium/main/install.sh | bash
```

## Use
Ask your agent in plain words, and the fium skill picks the step. The steps go around in a loop:
- **Start.** "Start a project that does X": it makes the repo from the templates and writes the goals first.
- **Finish.** "Is this done?": `fium done` measures every number in the project's goals where the change started and now, and asks you only when a number grows more than you allow.
- **Learn.** "Learn from this week's sessions": `fium learn` finds where agents failed, retried or were corrected, ranks it, and keeps each fix as a check.
- **Improve.** "Improve perch overnight": it tries one idea at a time in a worktree, keeps what makes the numbers better, reverts the rest, and logs why. You merge the keeps.
- **Discover.** "Can a newcomer use perch?": each kind of user tries their job with only what they'd have, and what stops them is kept and checked again next time.

The smallest way to try it: "Bring perch in line". The agent fixes what the checker finds, one rule at a time. For one goal across several repos, use `/fium across <goal>`. It researches, plans, runs one session per repo, and merges after your yes.

To see where your repos stand yourself:
```bash
fium check --all ~/Documents
fium status
```
