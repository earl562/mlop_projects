---
name: plotlot-branch-awareness
description: "Use when starting work in the plotlot-v2 repo. Checks the active git branch and reports uncommitted/stashed work before any code changes are made."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [macos]
metadata:
  hermes:
    tags: [plotlot, git, branch, awareness]
    related_skills: []
---

# PlotLot Branch Awareness

## Overview

The PlotLot repo (`plotlot-v2`) is shared across multiple branches and contributors. Each session starts on whatever branch was last checked out on disk — there's no per-session branch isolation. This skill ensures you always confirm the active branch before modifying any code.

## When to Use

- **Always** when you're about to read or edit files inside `/Users/aaliyahmatthews/Desktop/plotlot/plotlot-v2/`
- **Always** before running a command with side effects (write_file, patch, git add/commit/push, terminal commands that modify files)
- **Always** at the very start of any session where plotlot-v2 work is expected

Do NOT use this skill for:
- Read-only operations (reading files, searching, web lookups)
- Working outside the plotlot-v2 repo

## Procedure

### 1. Check the Active Branch

Run the following at the start of any session where you plan to work on PlotLot:

```bash
cd /Users/aaliyahmatthews/Desktop/plotlot/plotlot-v2 && git branch --show-current
```

### 2. Report Status to the User

Report the current branch, any modified/untracked files, and any stashed work in a single concise message. Example:

> "You're on the **Phat** branch, synced with origin/Phat. No uncommitted changes. No stashed work."
>
> or
>
> "You're on the **pi-feature-branch**, 36 commits ahead of origin with 9 modified files. There's stashed work from a prior session at stash@{0}."

### 3. Ask Before Proceeding

Before making any code changes, confirm with the user that the branch is correct:

> "Stay on this branch, or switch to another?"

If the user says to switch, do `git stash` if there's uncommitted work, then `git checkout <branch>`.

### 4. After Any Session That Switched Branches

If you performed a `git checkout` mid-session, the working tree on disk is now on that branch. Make a mental note (or save to memory) that future sessions will start on this new branch until someone switches again.

## Common Pitfalls

1. **Assuming the branch from a prior session is still active.** The branch on disk is shared state — another session or another user may have switched it.
2. **Checking out a branch with uncommitted changes without stashing.** Always stash or commit dirty work before switching, or git will reject the checkout.
3. **Making code changes on the wrong branch because you skipped the check.** This is the primary failure mode this skill is designed to prevent.
4. **Forgetting that stashed work is per-repo, not per-branch.** All stashes are visible regardless of current branch — don't assume a stash belongs to the current branch without confirming.

## Verification Checklist

- [ ] Ran `git branch --show-current` from the plotlot-v2 root
- [ ] Reported branch name, dirty/untracked state, and stash list to the user
- [ ] Received explicit confirmation or branch-switch instruction before any code modification
- [ ] If switched branches, verified the checkout succeeded and stashed any dirty work first
