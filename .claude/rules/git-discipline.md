---
description: Git commit conventions and branch discipline for EP monorepo
globs: *
---

# Git Discipline

## Commit Messages
- Format: `type: short description` (lowercase, no period)
- Types: `feat`, `fix`, `refactor`, `test`, `docs`, `ci`, `chore`, `perf`
- Scope with project prefix for clarity: `feat(plotlot): add Palm Beach property lookup`
- Keep subject line under 72 characters
- Body (optional): explain WHY, not WHAT. The diff shows what changed.

## Authorship
- All commits under Earl Perry's name only.
- **Never add `Co-Authored-By` trailers.** This is non-negotiable.
- Do not modify git config (name, email, signing).

## Branch Conventions
- `main` is the production branch. Auto-deploys to Render + Vercel.
- Feature branches: `feat/short-description` (e.g., `feat/palm-beach-lookup`)
- Fix branches: `fix/short-description` (e.g., `fix/sse-heartbeat-timing`)
- Always branch from `main`. Rebase before merging.

## PR Discipline
- Keep PRs focused — one feature or fix per PR.
- PR title matches commit message format.
- Include test coverage for all changes.
- Squash merge to `main` for clean history.

## What NOT to Commit
- `.env` files (use `.env.example` as template)
- `__pycache__/`, `.mypy_cache/`, `node_modules/`
- Large binary files (images, models, datasets)
- MLflow artifacts or database dumps
- IDE-specific files (`.vscode/`, `.idea/`)
