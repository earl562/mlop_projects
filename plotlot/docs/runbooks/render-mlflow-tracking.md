# Render MLflow Tracking Runbook

Use this runbook when PlotLot is healthy on Render but `/health` reports MLflow in
degraded-open mode with a schema-version warning.

## Current condition

As of May 19, 2026, the production Render service can be healthy while still
reporting:

```text
Detected out-of-date database schema (found version 008, but expected d3e4f5a6b7c8)
```

This happens when `MLFLOW_TRACKING_URI` points at the same Neon/Postgres database
as the app `DATABASE_URL`.

The PlotLot app uses its own Alembic revision table and currently reports app
schema revision `008`, while MLflow expects its own tracking schema head. Sharing
the same database creates schema/version-table drift even when the user-facing app
is otherwise healthy.

## Safe decision tree

1. If the goal is simply to stop the MLflow warning and tracing is optional:
   - move `MLFLOW_TRACKING_URI` off the shared app database
   - preferred fallback: local sqlite on Render
   - better long-term option: a dedicated tracking Postgres database
2. If the goal is to keep production MLflow on Postgres:
   - use a dedicated tracking database
   - only run `mlflow db upgrade` against that dedicated MLflow database
3. Do **not** blindly run `mlflow db upgrade` against the shared app database
   unless you have explicitly accepted the risk and taken a backup.

## Option A: Move MLflow to local sqlite on Render

This is the lowest-risk way to remove the warning.

Set Render env var:

```text
MLFLOW_TRACKING_URI=sqlite:///mlruns/mlflow.db
```

Then trigger a new deploy for `plotlot-api`.

Expected result:

- `/health` no longer reports MLflow schema mismatch
- tracing uses ephemeral local storage on the Render instance
- user-facing analysis stays unchanged

Tradeoff:

- MLflow data is not durable across instance replacement/redeploy

## Option B: Move MLflow to a dedicated Postgres database

Use this when you want durable MLflow tracking without coupling it to the app DB.

1. Provision a separate Postgres database.
2. Set Render env var:

```text
MLFLOW_TRACKING_URI=postgresql://<user>:<password>@<host>/<database>?sslmode=require
```

3. Run MLflow’s schema migration against that dedicated DB:

```bash
mlflow db upgrade postgresql://<user>:<password>@<host>/<database>?sslmode=require
```

4. Trigger a Render deploy.

Expected result:

- `/health` reports MLflow healthy
- app schema and MLflow schema evolve independently

## Option C: Upgrade MLflow in the shared app database

This is the highest-risk option and should only be used intentionally.

Prerequisites:

1. Take a backup/snapshot of the Neon database.
2. Confirm you are prepared to troubleshoot schema interference between app
   migrations and MLflow tracking tables.

Command:

```bash
mlflow db upgrade postgresql://<user>:<password>@<host>/<database>?sslmode=require
```

Expected result:

- the MLflow warning may clear

Risks:

- app and MLflow continue sharing one database surface
- future migrations can drift again
- a failed migration can impact the app database

## Verification

After any authorized production change:

1. Check Render deploy status.
2. Verify health:

```bash
curl -fsS https://plotlot-api.onrender.com/health
```

3. Confirm:
   - `status` is still `healthy`
   - `checks.database` is `ok`
   - `checks.mlflow` is no longer reporting the schema mismatch if you chose
     Option A or B

## Related repo checks

- `python3 scripts/deploy_doctor.py --fix-local-links`
  This now warns when Render points `MLFLOW_TRACKING_URI` at the same database as
  `DATABASE_URL`.
- `plotlot/render.yaml`
  The canonical Render blueprint now explicitly declares `MLFLOW_TRACKING_URI`.
