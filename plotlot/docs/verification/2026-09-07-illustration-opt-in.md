# Optional illustration checkpoint, September 7, 2026

## Scope and cause

On `cpt-pro` at `f64b0c52895f14c2b7d073bb22369d5d55f4fdb7`, the
[DB-backed browser run](https://github.com/earl562/plotlot-v2/actions/runs/34086791957)
failed because report navigation automatically posted to `/api/v1/render/building`.
The CI artifact recorded HTTP 503 from the unconfigured image provider. The
component's mount effect triggered the request; with credentials the existing
backend instead starts three image-generation calls.

This checkpoint removes that automatic request. Generate and Retry are explicit
actions. Changing envelope inputs starts an idle component session, preventing a
late response from the old session appearing in the new one. Returned view
selection makes no additional request. The panel explains possible provider
charges and that illustrations are not verified designs or zoning approvals.

The implementation reuses report color and surface tokens, 44px actions, visible
keyboard focus, status/error announcements and wrapping captions. Essential text
uses the existing secondary-text token for light/dark contrast. No provider,
authentication, dependency or backend-budget configuration is changed.

## Verification boundaries

The exact three-file code/test snapshot was exported independently of the mixed
working tree. Tested Git tree: `ec1d6516ee4e1ac3db203d6d0b8e7abc5c0fc7b4`.
Component Git blob: `62c11518e07829bdf42c90aedf48819f97acbc6a`.
This verification note is additional documentation, not part of that tested tree.

- Four regression tests failed on the original auto-fetch behavior, then passed
  after the repair: idle/input changes, explicit generation/view switching,
  explicit retry after failure, and late-response isolation.
- Isolated frontend suite: 44 passed. Production build, lint and type validation
  exited successfully; existing image-element and unused-code warnings remain.
- Isolated lookup browser suite: 5 passed, including navigation across all report
  tabs with zero optional render requests and the original strict console gate.
- Full isolated no-database browser suite: 22 passed. The mixed working-tree
  frontend suite also passed all 86 tests, type checking and scoped lint (one
  existing image-element warning), after the final component change.
- Unchanged isolated backend source/tests: Ruff passed and 453 files passed the
  format check. This is not a new backend runtime or production-provider test.
- Browser-state driver: 375, 768 and 1280px widths, 900px height, 24 valid PNG
  captures. Idle, keyboard focus, loading, error, front/aerial results are covered;
  desktop adds hover/loading frames and light/dark checks. Each viewport made zero
  image requests before an action, one explicit request yielding an injected 503,
  then one explicit retry yielding a labeled synthetic image. View selection
  added no request; no uncaught page errors occurred.

Real production-built `/workspace` components were exercised. Only analysis and
image-provider responses were synthetic fixtures. No model credits were spent;
these results do not establish image-provider availability or output quality.
The main reviewer inspected every final capture. Independent reviewers
`illustration_opt_in_integrity` and `illustration_opt_in_fidelity` each returned
PASS with high confidence, 24/24 capture coverage and no blocking findings,
stamped to the tested tree and component blob above. Their full reports are
retained in the task and the local task ledger. The existing floating scroll
control overlap was noted as unrelated UI debt, not waived as a new regression.

Local evidence is retained under
`/tmp/plotlot-image-checkpoint-20260907.72Itak/`: `capture-illustration.cjs`,
`evidence/receipts.json`, `evidence/image-diffs.json`, and the enumerated captures.
The contrast comparison reports matching dimensions and intact alpha at all
three widths, with expected text-area differences of 1.70%, 0.82% and 0.49%.
These scores are supporting evidence, not a whole-app accessibility certification.
Temporary screenshots, fixtures, credentials and generated build files are not
included in the commit.

## Still outside this checkpoint

Server-side illustration authorization, quotas/budgets, provider readiness,
in-flight cancellation and actual model quality remain release work. Existing
parent-report floor-plan assumptions, floating scroll controls and broader dark
theme debt are not repaired or certified here. This is not production approval.

The larger uncommitted results-first work remains separate: designated current
zoning-source routing/coverage, authoritative property and reviewed closed-sale
evidence across the Florida/NC launch markets, integration of the comp pipeline,
and remaining release gates. Sign-in configuration remains deferred. Pre-existing
design and analysis-evidence test files retain their small opt-in adaptations
with that backlog; they are not silently included in this isolated checkpoint.

## CI portability follow-up

The first published checkpoint, `94a44c930d49239ebb140d2c08940a4a24753cc5`,
passed GitHub's build, lint, backend quality and backend unit checks, but the new
late-response test failed on CI's Node 20: `Promise.withResolvers` is unavailable
there. Local verification used Node 26.3.0. The follow-up replaces only that test
helper with the standard Promise constructor, retaining every behavioral
assertion. The isolated 44-test suite, type checking and scoped lint pass again.
Rendered production code and its reviewed component blob are unchanged. CI's
actual Node 20 run remains the authoritative runtime-compatibility check.
