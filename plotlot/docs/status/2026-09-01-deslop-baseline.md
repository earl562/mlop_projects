# PlotLot De-Slop Baseline — 2026-09-01

## Source Baseline

```text
main:    0ce8fac57aeb1b688edb82474f9183e8eb6c9373
cpt-pro: a3531aed37b6d7186addc1ef3b8ee00ec5199778
work:    feat/cpt-pro-deslop
```

`main` remains the protected production branch. Cleanup work is based on `cpt-pro` and must not be merged to `main` until all required checks pass.

## Deterministic `cpt-pro` CI Baseline

Workflow run: `32423852874`

Passing jobs:

- Repo Hygiene
- Backend Quality: Ruff check, Ruff format check, mypy
- Backend Unit Tests with PostgreSQL
- Frontend Quality: lint, production build, UI tests
- Playwright No-DB

Failing job:

- Playwright DB-Backed

The database service started, all Alembic migrations through revision `015_leased_jobs_outbox` completed, the API passed `/health`, and three of four browser scenarios passed. The failing scenario was:

```text
plotlot/frontend/tests/lookup.db.spec.ts:24
Canonical db-backed lookup lane › lookup renders canonical report sections
```

Observed browser evidence:

```text
Unexpected console error: Failed to load resource:
the server responded with a status of 503 (Service Unavailable)
```

The failure reproduced on retry. This is an application/request-path defect after successful database migration and health preflight; it is not the earlier missing-table setup defect.

The Repository Pair Release Gate was skipped because it depends on the DB-backed Playwright job.

## Nightly Operational Baseline

Workflow run: `33522002201` on `main`, September 1, 2026.

### Deployed API Health

The workflow used the default endpoint:

```text
https://plotlot-api.onrender.com/health
```

The single `urllib.request.urlopen(..., timeout=15)` attempt ended with `TimeoutError: The read operation timed out`. No HTTP status or response body was received. The current check cannot distinguish a Render cold start from a sustained application outage.

### Live Provider Health

Command:

```bash
uv run python -m pytest \
  tests/integration/test_hub_live.py \
  tests/integration/test_universal_validation.py \
  -m live -v --tb=short
```

Result:

```text
5 failed, 2 passed in 113.40s
```

Failures:

1. Miami-Dade parcel discovery returned no candidate that passed coverage validation.
2. Broward parcel discovery returned no candidate that passed coverage validation.
3. Universal Miami-Dade lookup returned `None` while the legacy provider returned data.
4. Broward legacy ArcGIS lookup timed out.
5. Universal Palm Beach lookup returned `None` while the legacy provider returned data.

Existing logs report only the final rejection, not the candidate URL, validation score, field coverage, geometry support, elapsed time, or individual rejection reasons. Provider fixes require diagnostic evidence before validation rules or timeouts are changed.

## Baseline Rules

- These failures remain visible until reproduced and fixed at their source.
- Tests may not be skipped or allowlisted to create a green build.
- Provider validation may not be weakened globally without a failing fixture that proves the current rule is incorrect.
- The deployed health probe may add bounded retries and evidence but may not silently downgrade failure to success.
- Cleanup commits are evaluated against this baseline so pre-existing failures are not attributed to unrelated refactors.
