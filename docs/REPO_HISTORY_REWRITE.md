# Repository History Rewrite Recovery

This repository was rewritten to purge committed screenshots, Playwright outputs, and other generated media from `main`.

## What Changed

- media files were removed from git history
- generated report directories were purged from history
- repository hygiene rules now block those files from being tracked again

## Recommended Recovery

The safest recovery path is a fresh clone:

```bash
git clone https://github.com/earl562/mlop_projects.git
```

If you already have a local clone and do not need to preserve unpublished work:

```bash
git fetch --all --prune
git switch main
git reset --hard origin/main
```

## If You Have Local Work

Before resetting your local clone, save your unpublished work on a temporary branch or patch file.

Typical recovery flow:

```bash
git fetch --all --prune
git switch -c backup/pre-rewrite-main
git switch main
git reset --hard origin/main
```

Then re-apply your unpublished work by cherry-picking, rebasing, or copying over the small set of files you still want.

## New Repository Policy

- screenshots and large generated media do not belong in git history
- Playwright HTML reports and traces belong in workflow artifacts or ignored local output directories
- local walkthrough captures should use Playwright test output paths, not tracked repo folders
