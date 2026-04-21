# VC Readiness E2E Report

Date: 2026-04-20  
Target: VC meeting (Wednesday, 2026-04-22)

## Snapshot

- Frontend no-db lane: passing
- VC walkthrough (no-db + stubs): passing
- Backend health: degraded when the local database is unavailable
- Agent credentials can be present while upstream quota or billing still blocks completions

## Backend Health

Observed locally on 2026-04-20:

- `GET /health` returned `degraded`
- database target was `localhost:5433`
- `db_backed_analysis_ready` was false
- `portfolio_ready` was false
- `agent_chat_ready` was true

This report intentionally preserves the operational facts without storing screenshot artifacts in the repository.

## Test Runs

1. No-db smoke + mutation lane

```bash
cd plotlot/frontend
npm run test:e2e:no-db
```

Result: `9 passed`

2. VC walkthrough (no-db + stubs)

```bash
cd plotlot/frontend
npm run test:e2e:vc
```

Result: `1 passed`

## Observed Walkthrough States

- lookup welcome
- deal-type gate
- pipeline approval
- pipeline running
- agent welcome
- agent error state
- lookup after switching back

## Artifact Policy

- Playwright HTML reports belong in ignored local output directories
- traces and videos belong in CI artifacts or local ignored outputs
- screenshot evidence should not be committed to git history

## Next Steps Before Demo Use

1. Restore Postgres on `localhost:5433` for db-backed flows.
2. Re-check `GET /health` until the service reports `healthy`.
3. Run `npm run test:e2e:db` once the database is back.
4. Re-check agent credentials and quota if live completions are required for a demo.
