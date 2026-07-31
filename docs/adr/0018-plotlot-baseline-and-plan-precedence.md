# ADR 0018: PlotLot baseline and plan precedence

- Status: Accepted
- Date: 2026-07-25
- Decision owner: PlotLot production agentic harness MVP

## Context

The recoverable PlotLot source is a dirty worktree on
`feature/harness-wiring`. Its committed branch also contains unrelated
research, generated media, private execution records, and superseded planning
material. Copying that tree wholesale would mix product dependencies with
unreviewed user state and could archive credentials.

The authoritative implementation plan is
`.omo/plans/plotlot-production-agentic-harness-mvp.md` in the read-only source.
It supersedes unfinished PlotLot and ByRight product, market, and release work.
Completed ByRight Tasks 1, 2, 4, and 37 remain reusable evidence only after
their current inputs and outputs are revalidated under the authoritative plan.

## Decision

The PlotLot integration branch is frozen from two immutable inputs:

1. the clean source branch and full commit product tree recorded as
   `baseline_records` in `scripts/integration/plotlot_import_allowlist.json`;
   and
2. the exact dirty product files recorded as archive `records`, bound by path,
   SHA-256, POSIX mode, byte size, and file kind.

Every clean baseline path belongs to exactly one reviewed dependency class:

- `plotlot/src/**` is the transitive runtime closure for the approved MVP;
- `plotlot/tests/**` characterizes and protects that runtime;
- `plotlot/frontend/src/**` contains coupled customer-host UI behavior;
- `plotlot/frontend/tests/**` protects the imported host UI;
- `plotlot/alembic/versions/**` supplies schema dependencies;
- `plotlot/pyproject.toml` and `plotlot/uv.lock` bind install and resolution;
- `plotlot/.env.example` documents configuration names without secret values.

No other source path is imported. In particular, `.omo`, earlier evidence,
caches, environments, `node_modules`, credentials, `.env`, dumps, generated
media, private progress files, and unrelated education or research documents
are excluded. A secret-shaped value, unlisted archive member, changed
allowlist hash, malformed manifest, or escaping symlink blocks the operation.

The 410 reviewed dirty product paths are archived but not imported. Their
unchanged characterization produced three Ruff failures and 35 unit failures,
while a no-local disposable clone of source HEAD passed Ruff and all 1,872
unit tests. Under this plan's stale-state and precedence rules, no dirty subset
is admissible without independent dependency review and a green
characterization. Therefore `imported_dirty_records` is intentionally empty;
this is a fail-closed decision, not a claim that unfinished dirty work is done.

The committed delta contains 197 product paths whose bytes match the clean
source-HEAD records. The larger 511-record baseline manifest also verifies
unchanged product dependencies that did not need a commit delta.

Ignored paths are discovered with Git during capture, import, and verify.
Only explicit generated/private shapes such as environments, dependency
directories, caches, local databases, and build/test outputs are permitted.
An ignored path outside that policy fails closed; the CLI exercises this with
a scoped disposable Git repository rather than a synthetic unconditional
error.

Tracked generated/private state is forbidden independently of `.gitignore`.
The baseline removes local SQLite state and runtime health/watchdog logs, and
validation rejects any tracked database, cache, environment, credential,
runtime log, or evidence artifact before accepting the clone.

The private archive and receipts live outside Git under the shared task
artifact root. `scripts/integration/plotlot_freeze_baseline.py` is the
repository-owned capture, import, restore, and validation command. Archive
completion is atomic: an interruption cannot emit a valid completion receipt.

## Consequences

The source worktree remains read-only and its full dirty/Git fingerprint must
match before and after validation. The integration clone contains no Git
alternates and may not share any Git object inode with the source. Future work
must start from the committed integration baseline, not from the dirty source.

Any source update requires a new reviewed path set, manifest, private archive,
restore proof, source-unchanged receipt, and baseline commit. A previous
manifest or archive is stale evidence and cannot be reused.
