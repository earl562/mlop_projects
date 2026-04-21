# Branch Delivery Workflow

This repository should use a branch-first delivery model.

## Goal

- day-to-day work happens on separate development branches
- every pushed branch gets CI
- each development branch promotes into `main` through a pull request
- `main` stays approval-gated and release-ready

## Branch Types

Recommended branch prefixes:

- `codex/*` for agent-driven implementation work
- `dev/*` for general development branches
- `feat/*` for feature work
- `fix/*` for bug fixes
- `hotfix/*` for urgent repair work

## Delivery Flow

1. Create a development branch from `main`.
2. Commit and push continuously to that branch while work is in progress.
3. GitHub Actions runs CI on every push to supported development branch patterns.
4. The repo auto-opens a draft PR from that branch into `main` if one does not already exist.
5. When the branch is ready, mark the PR ready for review.
6. Collect approval.
7. Merge to `main`.

`main` should be treated as the approved integration branch, not the branch where ongoing implementation happens.

## What The Repo Enforces

From repo code and workflows:

- CI runs on pushes to `codex/*`, `dev/*`, `feat/*`, `fix/*`, and `hotfix/*`
- draft PRs to `main` are auto-opened for those branches
- CODEOWNERS points review at `@earl562`
- PR templates reinforce the approval checklist
- repo hygiene blocks generated media and Playwright outputs from being committed

## What Must Still Be Enabled In GitHub Settings

GitHub branch protection / rulesets are not fully stored in the repository, so enable these in the GitHub UI for `main`:

- require pull requests before merging
- require at least one approval
- require status checks to pass before merging
- require branches to be up to date before merging
- restrict direct pushes to `main`
- optionally require CODEOWNERS review

## Recommended Main Policy

- no direct commits to `main`
- no ongoing feature work on `main`
- `main` advances only through reviewed PRs
- production deployment remains tied to `main`
