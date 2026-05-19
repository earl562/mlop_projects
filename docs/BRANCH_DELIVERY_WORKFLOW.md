# Branch Delivery Workflow

This repository should use a branch-first delivery model.

## Goal

- day-to-day work happens on separate development branches
- every pushed branch gets CI
- each development branch promotes into `main` through a pull request
- `main` stays PR-gated, status-check-gated, and release-ready

## Branch Types

Recommended branch prefixes:

- `codex/*` for agent-driven implementation work
- `dev/*` for general development branches
- `feat/*` for feature work
- `fix/*` for bug fixes
- `hotfix/*` for urgent repair work

## Delivery Flow

1. Create a development branch from `main`.
2. Commit continuously to that branch while work is in progress.
3. Run `make deploy-doctor` from the repo root to catch root-directory, Vercel-link, and Render-service drift before shipping.
4. Run `make verify-local` from the repo root.
5. Run `make ship-branch` from the repo root. This pushes the branch and opens or reuses a draft PR into `main`.
6. GitHub Actions runs CI on every push to supported development branch patterns.
7. When the branch is ready, mark the PR ready for review.
8. If collaborators are involved, collect approval before merging.
9. Merge to `main` only after the required checks pass and the owner is satisfied with the promotion.

`main` should be treated as the verified integration branch, not the branch where ongoing implementation happens.

## What The Repo Enforces

From repo code and workflows:

- CI runs on pushes to `codex/*`, `dev/*`, `feat/*`, `fix/*`, and `hotfix/*`
- draft PRs to `main` are auto-opened for those branches when repository settings allow GitHub Actions to create pull requests
- CODEOWNERS points review at `@earl562`
- PR templates reinforce the approval checklist
- repo hygiene blocks generated media and Playwright outputs from being committed

## What Must Still Be Enabled In GitHub Settings

GitHub branch protection / rulesets are not fully stored in the repository, so enable these in the GitHub UI for `main`:

- enable `Allow GitHub Actions to create and approve pull requests`
- require pull requests before merging
- if your team has multiple reviewers, require at least one approval
- require status checks to pass before merging
- require branches to be up to date before merging
- restrict direct pushes to `main`
- optionally require CODEOWNERS review

## Recommended Main Policy

- no direct commits to `main`
- no ongoing feature work on `main`
- `main` advances only through PRs with passing required checks
- production deployment remains tied to `main`

## Canonical Deploy Roots

- Render backend service: repo root `plotlot/`
- Render Dockerfile path (relative to Render root): `./Dockerfile`
- Vercel frontend root directory: `plotlot/frontend`
- local `.vercel` links under legacy roots such as `frontend/.vercel` or `apps/plotlot/frontend/.vercel` should be removed
