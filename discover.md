# Discover

Find out whether the people a project is for can do what its goals promise: each kind of user tries their job with only what they'd have, and what stops them becomes a finding you can re-run. You manage; one session per user does the trying. Cite rule ids as in SKILL.md.

## 1. Users
GOALS.md's opening names 2 or 3 users, one line each: who `comes from` what they already use or know (what it has to beat), their `job` (one goal, in their words), what each `starts with` (the README, the install line, a phone and a photo), and what they `gives up when`. Tell them apart by where they come from, never by a name or an age. Each is `(guessed)` until a real one shows up in an issue, a session or a message.

There are three kinds: a person using it directly, an agent calling it, and a person who gets it through their agent. For an agent, a fresh session with only the README and the skill is the real user, not a stand-in.

A project that names no users: propose them and ask before anything runs.

## 2. One approval up front
Reply once (W1) with the project, its users, each one's job, where each runs, and the cost in tokens, turns and wall time (L1).

## 3. One session per user
- A fresh session on a cheaper model than yours, briefed with only what that user starts with and their job: never a list of things to probe, the other users' findings, or what you already suspect. Users who were told what to try agree with each other and prove nothing.
- It runs where the user isn't looking (L3), in a throwaway home and folder, installed the way the README says.
- When what a user comes from runs and does the same job, a second session, briefed the same way, tries the job with that. Where it gets them further than the project is a finding.
- It ends when the job is done or when that user gives up. Giving up is a result: record the step.
- A finding is what they did (a command or a step), what came back, verbatim, and what the docs promised. No minutes, scores or feelings: nobody measured them.

## 4. Check what came back
- Re-run every finding yourself. Drop what doesn't reproduce, and anything a session called working without output that shows it.
- Read each session's calls. Drop what came from a file that user wouldn't open, like the source.
- A doc that disagrees with the product is a finding, whichever is right.

## 5. Keep
Rows go in `~/.fium/discover/<repo>/findings.jsonl`, never in the repo, since verbatim output carries home paths and other projects' names: `{"user", "job", "did", "saw", "expected", "status": "open"}`. The next run re-runs each row first and reports it as fixed or still there, then looks for new ones.

## 6. Fix
Each fix is its own change, test first (W2), placed where the user is when it fails (S1): an error that names the fix before a line in a doc.

## 7. Report
Per user: whether they finished, where they stopped, and each finding, in plain words (W4). With simulated people it shows what breaks, not how a real person feels or how long they take.

Never inside a run: change the product, send, publish or sign up for anything.
