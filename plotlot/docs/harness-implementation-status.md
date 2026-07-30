# PlotLot Harness Implementation Status

Date: 2026-06-27

This document records the current production-harness slice implemented in fixture mode.
It is intentionally narrow: the full harness spec remains larger than this change.
Current goal scope excludes production private transcript storage and user-upload media
workflows as active blockers for this milestone. Reports and report export remain
preliminary and fixture-safe until live verification is completed, so final lender-grade
packages from live verified sources are still out of scope. The active product task is
web lookup/chat-agent parity through shared harness tools where matching harness tools
exist.

## Implemented

- Shared harness contracts under `src/plotlot/harness/contracts/` for run events,
  source catalog entries, evidence, GIS records, training records, reports, skills,
  tools, policy decisions, verification results, workflow templates, and usage ledgers.
- Full harness registries in `src/plotlot/harness/full_harness_registry.py` and
  `src/plotlot/harness/full_harness_registry_data.py` for required skills, agent roles,
  and tool specs.
- Existing `src/plotlot/harness/policy.py` now authorizes full-harness `ToolSpec`
  metadata through `HarnessPolicyRequest`, mapping registry permissions to deterministic
  allow, approval-required, or denied `PolicyDecision` outcomes. Registry metadata now
  includes explicit ask/deny examples for report export, user-media transcription, and
  protected media download attempts.
- Harness-native tool routing in `src/plotlot/harness/tool_router.py` and
  `src/plotlot/harness/tool_router_handlers.py` executes registered `ToolSpec` entries
  only through policy checks, emits typed `tool.requested`, `tool.policy_checked`,
  `tool.started`, `tool.completed`, `tool.approval_required`, `tool.denied`, and
  `tool.failed` events, and reuses deterministic fixture handlers for Municode, South
  Florida GIS search, training discovery, and underwriting calculators.
- Local JSON-backed tool-call ledger in `src/plotlot/harness/tool_call_store.py`
  persists routed tool calls with args, policy decisions, result payloads, status,
  errors, and evidence links. CLI and REST tool calls append their typed tool events to
  existing persisted runs when a matching run ID exists. The default path is
  `${XDG_STATE_HOME:-~/.local/state}/plotlot/harness-tool-calls.json` and tests can
  override it with `PLOTLOT_HARNESS_TOOL_CALL_STORE_PATH`.
- South Florida GIS fixture lane in `src/plotlot/harness/south_florida_gis.py` with
  Miami-Dade and Broward fixture adapters under one shared source-lane architecture.
- Broward BMSD applicability classification that marks BMSD zoning as contextual or
  requiring municipal verification for municipal sites.
- Municode ordinance fixture lane in `src/plotlot/harness/municode_source.py` with
  Florida section search, section retrieval, deterministic rule extraction, source
  catalog entries, and ordinance evidence creation. Fixture ordinance evidence is always
  marked `requires_official_verification`.
- Training ingestion fixture lane in `src/plotlot/harness/training_ingestion.py` with
  YouTube ARV/comps/offer discovery, transcript segmentation, concept extraction,
  workflow mapping, and search.
- Fixture run builder in `src/plotlot/harness/fixture_runs.py` that emits typed ordered
  events and preliminary fixture-mode run output.
- Local JSON-backed run/event store in `src/plotlot/harness/run_store.py` with run
  lookup, ordered event retrieval, run listing, replay timeline export, and state-machine
  cancellation for queued/running/waiting-for-approval runs. Cancellation contracts and
  event construction live in `src/plotlot/harness/run_cancellation.py`; successful and
  blocked cancellation attempts emit typed `run.cancelled` events. The default path is
  `${XDG_STATE_HOME:-~/.local/state}/plotlot/harness-runs.json` and tests can override it
  with `PLOTLOT_HARNESS_STORE_PATH`.
- Local JSON-backed evidence ledger in `src/plotlot/harness/evidence_store.py` with
  fixture evidence creation in `src/plotlot/harness/fixture_evidence.py` and shared run
  persistence in `src/plotlot/harness/run_persistence.py`. The default path is
  `${XDG_STATE_HOME:-~/.local/state}/plotlot/harness-evidence.json` and tests can
  override it with `PLOTLOT_HARNESS_EVIDENCE_STORE_PATH`.
- Shared claim/report contracts in `src/plotlot/harness/contracts/` plus a local
  JSON-backed claim/report ledger in `src/plotlot/harness/report_store.py`. Fixture
  reports and source-grounded claims are generated deterministically in
  `src/plotlot/harness/fixture_reports.py`. The default path is
  `${XDG_STATE_HOME:-~/.local/state}/plotlot/harness-reports.json` and tests can
  override it with `PLOTLOT_HARNESS_REPORT_STORE_PATH`.
- Shared verification contracts in `src/plotlot/harness/contracts/`, deterministic
  report verification in `src/plotlot/harness/verification.py`, local JSON-backed
  verification persistence in `src/plotlot/harness/verification_store.py`, and report
  finalization gating in `src/plotlot/harness/report_finalization.py`. Fixture/mock
  evidence blocks finalization while preserving preliminary reports and fixture-safe
  exports pending live verification. The default path is
  `${XDG_STATE_HOME:-~/.local/state}/plotlot/harness-verifications.json` and tests can
  override it with `PLOTLOT_HARNESS_VERIFICATION_STORE_PATH`.
- Local replay/debug bundle export in `src/plotlot/harness/debug_bundle.py`, joining run
  metadata, ordered events, tool calls, evidence, claims, calculations, reports,
  verification results, local approvals, approval events, and run-linked memory records
  while explicitly omitting secrets and full transcript text.
- Local JSON-backed approval ledger in `src/plotlot/harness/approval_store.py` with typed
  `approval.requested`, `approval.granted`, and `approval.denied` events. The CLI and
  REST harness surfaces can request, list, inspect, approve, and deny fixture/local
  approvals without bypassing the existing DB-backed production approval routes. The
  default path is `${XDG_STATE_HOME:-~/.local/state}/plotlot/harness-approvals.json`
  and tests can override it with `PLOTLOT_HARNESS_APPROVAL_STORE_PATH`.
- Local JSON-backed project memory ledger in `src/plotlot/harness/memory_store.py` with
  typed `MemoryItem` records for site assumptions, prior decisions, open questions,
  report/lender preferences, user overrides, budget notes, contractor notes, and
  training workflow preferences. Memory can link to source run IDs and evidence IDs but
  is explicitly marked `is_evidence: false`; it is inspectable/editable from
  `src/plotlot/cli_harness_memory.py` and `src/plotlot/api/harness_memory.py`. The
  default path is `${XDG_STATE_HOME:-~/.local/state}/plotlot/harness-memory.json` and
  tests can override it with `PLOTLOT_HARNESS_MEMORY_STORE_PATH`.
- Harness health collector in `src/plotlot/harness/health.py` covering registry load,
  local store path readiness, South Florida GIS fixture catalog load, training fixture
  catalog load, local queue readiness, CLI availability, and optional Codex CLI presence.
  REST health views are exposed from `src/plotlot/api/harness_health.py`; `plotlot doctor`
  prints the same collector output.
- Fixture-mode eval runner in `src/plotlot/harness/evals.py`,
  `src/plotlot/harness/eval_models.py`, and `src/plotlot/harness/eval_suites.py` with
  deterministic suites for harness trajectory, evidence linkage, Municode ordinance,
  South Florida GIS, underwriting calculators, training discovery/workflow mapping, and
  harness health.
  `src/plotlot/cli_harness_evals.py` exposes `plotlot eval suites` and
  `plotlot eval run [--suite SUITE]` with CI-friendly exit codes.
- Scaffold contracts in `src/plotlot/harness/contracts/scaffold.py` and a safe tool
  scaffolder in `src/plotlot/harness/scaffold.py`. `plotlot scaffold tool TOOL_NAME`
  generates a compile-safe tool contract, handler with `TOOL_SPEC`, manifest, fixture,
  policy metadata, unit test, and docs stub. Existing files are never overwritten unless
  `--force` is supplied.
- Optional Codex operator lane in `src/plotlot/harness/codex_reference.py` and
  `src/plotlot/cli_harness_codex.py`. It can generate/print PlotLot goal prompts,
  inspect a local Codex checkout, report local Codex CLI availability, and run Codex
  non-interactively through `codex exec -` when explicitly invoked. The lane is
  documented in `docs/codex-cli-reference.md` and is not a production runtime dependency.
- Local JSON-backed job queue in `src/plotlot/harness/job_queue.py` with queued analysis
  jobs, idempotency keys, job lifecycle events, local job cancellation, worker execution
  via the same fixture runtime, retry scheduling, terminal dead-letter handling, and
  run/evidence persistence through the shared stores.
  Worker event envelope construction is split into `src/plotlot/harness/job_queue_events.py`;
  job models and cancellation event construction live in `src/plotlot/harness/job_models.py`
  and `src/plotlot/harness/job_cancellation.py`. The default path is
  `${XDG_STATE_HOME:-~/.local/state}/plotlot/harness-jobs.json` and tests can override it
  with `PLOTLOT_HARNESS_JOB_STORE_PATH`.
- Harness-native deterministic underwriting calculators in
  `src/plotlot/harness/underwriting_calculators.py` and typed calculator contracts in
  `src/plotlot/harness/underwriting_models.py` for feasibility, NOI/as-built value,
  residual land value, BRRRR refinance, construction budgets, and sensitivity.
- Shared calculation execution and ledger persistence in
  `src/plotlot/harness/calculation_runner.py` and
  `src/plotlot/harness/calculation_store.py`. The default local ledger path is
  `${XDG_STATE_HOME:-~/.local/state}/plotlot/harness-calculations.json` and tests can
  override it with `PLOTLOT_HARNESS_CALCULATION_STORE_PATH`.
- REST harness routes in `src/plotlot/api/harness.py` registered through
  `src/plotlot/api/router_registry.py`.
- REST tool routes in `src/plotlot/api/harness_tools.py` for `GET /api/v1/harness/tools`,
  `GET /api/v1/harness/tools/:toolName`, and
  `POST /api/v1/harness/tools/:toolName/call`, all backed by the same `ToolRouter` and
  policy engine as the CLI. `GET /api/v1/harness/runs/:runId/tool-calls` lists
  persisted routed tool calls for a run.
- Existing chat/web lookup tooling now exposes full-harness source tools through
  `src/plotlot/api/chat_harness_bridge.py`: `search_municode`, `get_municode_section`,
  `extract_ordinance_rules`, `search_south_florida_gis`, and
  `discover_rehabvaluator_video_sections` all execute through the shared
  `HarnessToolRouter`, policy engine, fixture source lanes, and typed tool event trace.
  Legacy chat governance recognizes those names through
  `src/plotlot/harness/full_harness_chat_contracts.py`.
- Chat web lookup now routes `web_search` through the shared default harness runtime when
  chat has a `ToolContext`, and both chat fallback execution and the runtime handler use
  `src/plotlot/harness/web_lookup.py` for Jina status handling, no-key guidance,
  quota/auth errors, and result normalization. This route is part of the current
  chat-agent parity track.
- Chat indexed zoning search now routes context-aware `search_zoning_ordinance` calls
  through the shared default harness runtime. Legacy chat fallback execution and the
  runtime handler both use `src/plotlot/harness/ordinance_lookup.py` for indexed
  ordinance search, zone-code boosting, no-result anti-fabrication guidance, and
  runtime evidence creation. This route is part of the current chat-agent parity track.
- Chat property lookup now routes context-aware `lookup_property_info` calls through
  the shared default harness runtime. Runtime property results include the same zoning
  crosswalk and next-step guidance that chat previously generated locally, while chat
  still persists property context for follow-up ordinance searches. This route is part
  of the current chat-agent parity track.
- Full-harness MCP parity adapter in `src/plotlot/harness/full_harness_mcp.py` exposing
  full-harness tool specs, governed tool calls, and resource readers for tools, skills,
  source catalogs, training sources, run events, evidence, reports, and verification.
  It uses the same `HarnessToolRouter`, policy engine, source catalog, and local ledgers
  as the CLI/API surfaces. The default `plotlot-mcp` and `plotlot-harness-mcp` console
  scripts now both point at the governed FastMCP wrapper in
  `src/plotlot/mcp/harness_server.py`. The legacy stdio MCP server remains available
  explicitly as `plotlot-legacy-mcp`.
- REST evidence routes in `src/plotlot/api/harness_evidence.py`, plus fallback evidence
  lookup in the existing `src/plotlot/api/evidence.py` route, for persisted fixture
  evidence inspection by run ID or evidence ID.
- REST claim/report routes in `src/plotlot/api/harness_reports.py` for persisted fixture
  claim and report inspection by run ID, claim ID, or report ID, plus finalize and export
  endpoints. Finalization blocks fixture/mock reports; export writes a local markdown
  artifact, records the artifact URI on the report, and appends a typed `report.exported`
  event to the run log.
- REST verification routes in `src/plotlot/api/harness_verification.py` for persisted
  verifier results by run ID, report ID, or verification ID.
- REST debug bundle export at `GET /api/v1/harness/runs/:runId/debug-bundle`.
- REST calculator routes in `src/plotlot/api/harness_calculations.py` for feasibility,
  pro forma/NOI valuation, residual land value, BRRRR refinance, construction budget,
  sensitivity, persisted run calculations, and calculation lookup.
- CLI harness entrypoint in `src/plotlot/cli_harness.py` for doctor, skills, tools, GIS
  search, and training discovery. Run/history commands, job queue commands, and shared
  option parsing are split into `src/plotlot/cli_harness_runs.py`,
  `src/plotlot/cli_harness_jobs.py`, and `src/plotlot/cli_harness_support.py`.
  Calculator commands are split into `src/plotlot/cli_harness_calc.py`; evidence
  inspection commands are split into `src/plotlot/cli_harness_evidence.py`; claim/report
  inspection, local markdown export, and finalization commands are split into
  `src/plotlot/cli_harness_reports.py`;
  verification inspection commands are split into `src/plotlot/cli_harness_verification.py`;
  approval commands are split into `src/plotlot/cli_harness_approvals.py`; memory
  commands are split into `src/plotlot/cli_harness_memory.py`; tool inspection/call
  commands are split into `src/plotlot/cli_harness_tools.py`; `plotlot tools calls
  --run-id RUN_ID` lists persisted routed tool calls. Scaffold commands are split into
  `src/plotlot/cli_harness_scaffold.py`. TUI commands are split into
  `src/plotlot/cli_harness_tui.py` and render through the shared
  `src/plotlot/harness/tui.py` renderer. Run replay/debug bundle export is handled by
  `src/plotlot/cli_harness_runs.py`.
- Terminal-native TUI shell in `src/plotlot/harness/tui.py` with home, run monitor,
  evidence, verification, approvals, report, replay/debug, source catalog, and training
  corpus screens. The TUI consumes the same run store, evidence ledger, report ledger,
  verification ledger, approval ledger, tool-call ledger, debug bundle exporter, GIS
  source catalog, and training source catalog as the CLI/API surfaces. `plotlot tui
  --json` provides a stable smoke-testable payload; text mode prints a terminal workbench
  view. Screen rendering is split across `src/plotlot/harness/tui_home.py`,
  `src/plotlot/harness/tui_inspection.py`, `src/plotlot/harness/tui_approvals.py`, and
  `src/plotlot/harness/tui_replay_debug.py`.
- Typecheck cleanup for existing event, step, model, event-store, and calculator issues
  that were blocking `uv run mypy src`.

## Current Examples

## 2026-06-30 Excalidraw Goal Run Evidence

The Excalidraw-derived goal in `docs/goals/excalidraw-agentic-harness.goal.md`
has been started against the narrow MVP fixture lane.

What was run:

- Fixed the Miami Gardens fixture acquisition-memo path by giving the fixture a
  positive FAR default, so it exercises feasibility calculation instead of
  sending invalid `0.0` into the calculator.
- Updated the CLI gold-path expectation to include the current exit-comp support
  quality metrics:
  - `best_exit_fit_score`
  - `best_exit_price_variance_ratio`
  - `best_exit_qualification_score`
- Ran the Miami Gardens fixture acquisition memo through the CLI.
- Read the persisted run events, replay timeline, evidence ledger, report ledger,
  and verification ledger.
- Ran the queued local worker path for the same fixture address.

Observed fixture run:

```text
run_id: run_fixture_6384e636ed77
event count: 38
first event: run.created
last event: run.completed
completed tools:
  geocode_address
  lookup_property_info
  search_south_florida_gis
  search_municode
  find_comparables
  compute_feasibility
  run_noi_valuation
  run_residual_land_value
evidence items: 13
reports: 1 preliminary
verification: 1 blocked
```

Observed queued worker run:

```text
job_id: job_d103766b57e7
worker status: completed
job event count: 4
last job event: job.completed
```

Targeted verification:

```bash
uv run pytest \
  tests/unit/test_harness_cli.py::test_cli_run_miami_gardens_fixture_default_far_runs \
  tests/unit/test_harness_cli.py::test_cli_run_acquisition_memo_streams_events \
  tests/unit/test_harness_cli_gold_paths.py \
  tests/unit/test_harness_job_queue.py \
  tests/unit/test_harness_report_store.py \
  tests/unit/test_harness_verification_store.py \
  -q --tb=short
```

Result:

```text
30 passed, 1 warning
```

This is not yet the full goal completion gate. It proves the first implementation
slice can run through the harness surfaces in fixture mode, while report
verification correctly remains blocked because fixture evidence is preliminary.

CLI acquisition memo fixture run:

```bash
uv run plotlot run acquisition-memo \
  --address "example Miami-Dade fixture address" \
  --source-mode fixture \
  --assumption avgUnitSizeSf=850 \
  --assumption efficiencyFactor=0.85 \
  --assumption targetProfitPct=0.18 \
  --stream
```

CLI Broward GIS fixture search:

```bash
uv run plotlot gis search zoning --county Broward --json
```

CLI saved-run replay:

```bash
RUN_ID="$(uv run plotlot run zoning-research \
  --address "example Broward fixture address" \
  --source-mode fixture \
  | sed -n 's/.*"run_id": "\([^"]*\)".*/\1/p')"
uv run plotlot runs events "$RUN_ID"
uv run plotlot runs replay "$RUN_ID"
uv run plotlot runs export-debug-bundle "$RUN_ID"
uv run plotlot evidence list --run-id "$RUN_ID"
uv run plotlot claims list --run-id "$RUN_ID"
uv run plotlot reports list --run-id "$RUN_ID"
uv run plotlot verification list --run-id "$RUN_ID"
```

CLI run cancellation for cancellable statuses:

```bash
uv run plotlot runs cancel "$RUN_ID" \
  --reason "Duplicate run." \
  --actor-user-id analyst@example.test
uv run plotlot runs events "$RUN_ID"
```

Cancellation is accepted for queued, running, and waiting-for-approval runs. Completed
fixture runs fail with `run_cancellation_blocked` and still append a failed
`run.cancelled` audit event.

CLI routed tool call and persisted event trace:

```bash
uv run plotlot tools call search_municode \
  --run-id "$RUN_ID" \
  --workspace-id ws_fixture \
  --source-mode fixture \
  --json '{"jurisdiction":"miami","query":"parking"}'
uv run plotlot tools calls --run-id "$RUN_ID"
uv run plotlot runs events "$RUN_ID"
uv run plotlot runs export-debug-bundle "$RUN_ID"
```

CLI queued worker fixture run:

```bash
JOB_ID="$(uv run plotlot jobs create \
  --address "example Miami-Dade fixture address" \
  --analysis-type acquisition-memo \
  --source-mode fixture \
  --idempotency-key example-job \
  | sed -n 's/.*"job_id": "\([^"]*\)".*/\1/p')"
uv run plotlot jobs run-next
uv run plotlot jobs events "$JOB_ID"
```

CLI queued worker fixture failure and retry:

```bash
JOB_ID="$(uv run plotlot jobs create \
  --address "example Miami-Dade retry fixture address" \
  --analysis-type acquisition-memo \
  --source-mode fixture \
  | sed -n 's/.*"job_id": "\([^"]*\)".*/\1/p')"
uv run plotlot jobs run-next --fixture-failure "Synthetic worker failure."
uv run plotlot jobs events "$JOB_ID"
```

Expected worker failure output keeps the job `queued`, increments `attempts`, stores the
typed error summary, and appends `job.failed` followed by `job.retry_scheduled`.

CLI queued worker fixture dead-letter:

```bash
JOB_ID="$(uv run plotlot jobs create \
  --address "example Miami-Dade terminal failure fixture address" \
  --analysis-type acquisition-memo \
  --source-mode fixture \
  --max-attempts 1 \
  | sed -n 's/.*"job_id": "\([^"]*\)".*/\1/p')"
uv run plotlot jobs run-next --fixture-failure "Synthetic terminal failure."
uv run plotlot jobs events "$JOB_ID"
```

Expected terminal failure output marks the job `dead_lettered` and appends
`job.failed` followed by `job.dead_lettered`.

CLI queued job cancellation:

```bash
JOB_ID="$(uv run plotlot jobs create \
  --address "example Miami-Dade fixture address" \
  --analysis-type acquisition-memo \
  --source-mode fixture \
  | sed -n 's/.*"job_id": "\([^"]*\)".*/\1/p')"
uv run plotlot jobs cancel "$JOB_ID" \
  --reason "Duplicate queued job." \
  --actor-user-id analyst@example.test
uv run plotlot jobs events "$JOB_ID"
```

Job cancellation is accepted for queued and locally running jobs. Completed, failed,
cancelled, and dead-lettered fixture jobs fail with `job_cancellation_blocked` and still
append a failed `job.cancelled` audit event.

CLI persisted evidence lookup:

```bash
EVIDENCE_ID="$(uv run plotlot evidence list --run-id "$RUN_ID" \
  | sed -n 's/.*"evidence_id": "\([^"]*\)".*/\1/p' \
  | head -1)"
uv run plotlot evidence show "$EVIDENCE_ID"
```

CLI persisted claim/report lookup:

```bash
CLAIM_ID="$(uv run plotlot claims list --run-id "$RUN_ID" \
  | sed -n 's/.*"claim_id": "\([^"]*\)".*/\1/p' \
  | head -1)"
uv run plotlot claims show "$CLAIM_ID"
uv run plotlot reports show "report_${RUN_ID}"
```

CLI local report export:

```bash
uv run plotlot reports export "report_${RUN_ID}"
uv run plotlot runs events "$RUN_ID"
```

Expected export output includes `artifact_uri`, `file_path`, `content_type`, and
`export_format`. The persisted report `export_urls` includes the artifact URI, and the
run event stream includes `report.exported`.

CLI persisted verification and blocked finalization:

```bash
uv run plotlot verification show --report-id "report_${RUN_ID}"
uv run plotlot reports finalize "report_${RUN_ID}"
```

Fixture-mode finalization exits non-zero with `report_finalization_blocked` and the
blocking `verification_id`.

CLI local approval workflow:

```bash
APPROVAL_ID="$(uv run plotlot approvals request \
  --run-id "$RUN_ID" \
  --action export_lender_package \
  --risk-level high \
  --reason "Exporting a lender package requires analyst approval." \
  | sed -n 's/.*"approval_id": "\([^"]*\)".*/\1/p')"
uv run plotlot approvals list --run-id "$RUN_ID"
uv run plotlot approvals show "$APPROVAL_ID"
uv run plotlot approvals approve "$APPROVAL_ID" --resolved-by analyst@example.test
```

CLI local project memory workflow:

```bash
MEMORY_ID="$(uv run plotlot memory write \
  --workspace-id ws_fixture \
  --project-id project_fixture \
  --site-id site_fixture \
  --memory-type site_assumption \
  --content "Use 850 sf average unit size until official plans are provided." \
  --source-run-id "$RUN_ID" \
  --evidence-id "$EVIDENCE_ID" \
  | sed -n 's/.*"memory_id": "\([^"]*\)".*/\1/p')"
uv run plotlot memory list --workspace-id ws_fixture
uv run plotlot memory show "$MEMORY_ID"
uv run plotlot memory update "$MEMORY_ID" --content "Use 900 sf average unit size from sponsor update."
```

CLI residual land value calculator:

```bash
uv run plotlot calc residual-land-value --json '{
  "as_built_value": 1235000,
  "desired_profit": 150000,
  "hard_costs": 600000,
  "soft_costs": 90000,
  "contingency": 60000,
  "developer_fee": 30000,
  "closing_costs": 15000,
  "financing_costs": 40000,
  "holding_costs": 20000,
  "selling_costs": 35000,
  "asking_price": 175000
}'
```

CLI persisted calculation ledger:

```bash
CALC_ID="$(uv run plotlot calc residual-land-value \
  --run-id run_fixture_cli_calc \
  --json '{"as_built_value":1235000,"desired_profit":150000,"hard_costs":600000,"soft_costs":90000,"contingency":60000,"developer_fee":30000,"closing_costs":15000,"financing_costs":40000,"holding_costs":20000,"selling_costs":35000,"asking_price":175000}' \
  | sed -n 's/.*"calculation_id": "\([^"]*\)".*/\1/p')"
uv run plotlot calculations list --run-id run_fixture_cli_calc
uv run plotlot calculations show "$CALC_ID"
```

CLI YouTube ARV/comps/offer fixture discovery:

```bash
uv run plotlot training discover \
  --url 'https://www.youtube.com/watch?v=0IS1iFMJ8sQ' \
  --json
```

CLI harness doctor:

```bash
uv run plotlot doctor
```

CLI/TUI analyst workbench:

```bash
uv run plotlot tui
uv run plotlot tui --json
uv run plotlot tui --screen run-monitor --run-id "$RUN_ID"
uv run plotlot tui --screen evidence --run-id "$RUN_ID" --json
uv run plotlot tui --screen verification --run-id "$RUN_ID" --json
uv run plotlot tui --screen approvals --run-id "$RUN_ID" --json
uv run plotlot tui --screen approvals --approve "$APPROVAL_ID" --resolved-by analyst@example.test --json
uv run plotlot tui --screen approvals --deny "$APPROVAL_ID" --resolved-by analyst@example.test --json
uv run plotlot tui --screen report --run-id "$RUN_ID" --json
uv run plotlot tui --screen replay-debug --run-id "$RUN_ID" --json
uv run plotlot tui --screen source-catalog --json
uv run plotlot tui --screen training --json
```

CLI shared tool router:

```bash
uv run plotlot tools inspect search_municode
uv run plotlot tools call search_municode \
  --run-id run_fixture_tool \
  --workspace-id ws_fixture \
  --json '{"jurisdiction":"miami","query":"parking"}'
uv run plotlot tools call export_report \
  --run-id run_fixture_tool \
  --workspace-id ws_fixture \
  --json '{"report_id":"report_fixture"}'
```

The `export_report` fixture call exits non-zero with `status=approval_required` and a
deterministic approval ID; protected media download tools are denied before any handler.

CLI fixture eval runner:

```bash
uv run plotlot eval suites
uv run plotlot eval run --suite harness
uv run plotlot eval run
```

CLI tool scaffolding:

```bash
uv run plotlot scaffold tool example_tool --root .
uv run plotlot scaffold tool example_tool --root . --force
```

CLI optional Codex operator lane:

```bash
uv run plotlot codex goal generate
uv run plotlot codex goal print
uv run plotlot codex inspect-reference --path ../codex
uv run plotlot codex doctor
uv run plotlot codex run --goal docs/goals/full-harness.goal.md
```

CLI Municode fixture lane:

```bash
uv run plotlot municode search --jurisdiction miami --query parking
uv run plotlot municode section --section-id municode_miami_parking_fixture
uv run plotlot municode extract-rules --section-id municode_miami_parking_fixture
```

API fixture run endpoint:

```http
POST /api/v1/deal-analysis/run
Content-Type: application/json

{
  "address": "example Miami-Dade fixture address",
  "analysisType": "acquisition_memo",
  "sourceMode": "fixture",
  "assumptions": {
    "avgUnitSizeSf": 850,
    "efficiencyFactor": 0.85,
    "targetProfitPct": 0.18
  }
}
```

Expected response includes `run_id`, `status`, `events_url`, `report_id`,
`evidence_ids`, `verification_status`, `source_mode`, and `preliminary`.

API persisted run operations:

```http
GET /api/v1/harness/runs/:runId
GET /api/v1/harness/runs/:runId/events
POST /api/v1/harness/runs/:runId/replay
POST /api/v1/harness/runs/:runId/cancel
```

Cancellation returns the updated run on success, or HTTP 409 with
`run_cancellation_blocked` when the run status cannot transition to cancelled. Every
accepted or blocked cancellation attempt is persisted as `run.cancelled`.

API persisted job operations:

```http
POST /api/v1/harness/jobs
GET /api/v1/harness/jobs
GET /api/v1/harness/jobs/:jobId
GET /api/v1/harness/jobs/:jobId/events
POST /api/v1/harness/jobs/:jobId/cancel
POST /api/v1/harness/jobs/run-next
```

Job cancellation returns the updated job on success, or HTTP 409 with
`job_cancellation_blocked` when the job status cannot transition to cancelled. Every
accepted or blocked cancellation attempt is persisted as `job.cancelled`. Job creation
accepts `max_attempts` for the local retry budget; worker failures emit `job.failed`
and either `job.retry_scheduled` or `job.dead_lettered`.

API persisted evidence lookup:

```http
GET /api/v1/harness/runs/:runId/evidence
GET /api/v1/evidence/:evidenceId
```

Expected evidence responses include `evidence_id`, `run_id`, `source_type`,
`source_url`, `freshness_status`, `applicability`, `confidence`, and metadata.

API shared tool router:

```http
GET /api/v1/harness/tools/search_municode
POST /api/v1/harness/tools/search_municode/call
Content-Type: application/json

{
  "workspace_id": "ws_fixture",
  "run_id": "run_fixture_tool",
  "source_mode": "fixture",
  "args": {
    "jurisdiction": "miami",
    "query": "parking"
  }
}
```

Expected tool-call responses include `ok`, `tool_name`, `run_id`, `status`,
`tool_call_id`, `policy_decision`, `payload`, ordered `events`, and `source_mode`.
Persisted routed calls are available at:

```http
GET /api/v1/harness/runs/:runId/tool-calls
```

API persisted claim/report lookup:

```http
GET /api/v1/harness/runs/:runId/claims
GET /api/v1/claims/:claimId
GET /api/v1/harness/runs/:runId/reports
GET /api/v1/reports/:reportId
POST /api/v1/reports/:reportId/export
POST /api/v1/reports/:reportId/finalize
```

Expected claim/report responses include `claim_id`, `report_id`, `run_id`,
`evidence_ids`, `status`, `source_mode`, source-boundary metadata (`field_key`,
`kind`, `origin`, `source_url`, `next_verification_step`, `claim_freshness`),
report sections, and report claim IDs.
Report export writes a local markdown artifact, updates report `export_urls`, and appends
`report.exported` to the run event stream. Fixture-mode finalization returns HTTP 409
with `report_finalization_blocked`.

API persisted verification lookup:

```http
GET /api/v1/harness/runs/:runId/verification
GET /api/v1/reports/:reportId/verification
GET /api/v1/verification/:verificationId
```

Expected verification responses include `verification_id`, `status`, `checks`,
`missing_evidence`, `unsupported_claims`, `mock_or_fixture_blockers`, and `created_at`.
The verifier now treats authority claims with missing `source_url`, hypotheses without
`next_verification_step`, and verified facts with stale/unknown/unverified claim freshness as
unsupported even when an evidence ID exists, and exposes this through the
`claim_source_boundary` verification check.

API debug bundle export:

```http
GET /api/v1/harness/runs/:runId/debug-bundle
```

Expected debug bundle responses include `run`, `replay`, ordered `events`, `evidence`,
`tool_calls`, `claims`, `calculations`, `reports`, `verifications`, `approvals`,
`approval_events`, run-linked `memory`, and `redactions`.

API local approval workflow:

```http
POST /api/v1/harness/runs/:runId/approvals
Content-Type: application/json

{
  "requested_action": "export_lender_package",
  "risk_level": "high",
  "reason": "Exporting a lender package requires analyst approval.",
  "policy_ids": ["fixture-export-approval"]
}
```

```http
GET /api/v1/harness/runs/:runId/approvals
GET /api/v1/harness/approvals/:approvalId
POST /api/v1/harness/approvals/:approvalId/approve
POST /api/v1/harness/approvals/:approvalId/deny
```

Expected approval responses include `approval_id`, `run_id`, `requested_action`,
`risk_level`, `reason`, `status`, `requested_at`, `resolved_at`, `resolved_by`, and
policy/request/response payload metadata.

API local project memory workflow:

```http
POST /api/v1/harness/memory
Content-Type: application/json

{
  "workspace_id": "ws_fixture",
  "project_id": "project_fixture",
  "site_id": "site_fixture",
  "memory_type": "site_assumption",
  "content": "Use 850 sf average unit size until official plans are provided.",
  "source_run_id": "run_fixture_example",
  "evidence_ids": ["ev_fixture_example"]
}
```

```http
GET /api/v1/harness/memory?workspace_id=ws_fixture
GET /api/v1/harness/memory/:memoryId
PATCH /api/v1/harness/memory/:memoryId
```

Expected memory responses include `memory_id`, workspace/project/site scope,
`memory_type`, `content`, optional `source_run_id`, `evidence_ids`, editable metadata,
and `metadata.is_evidence=false`.

API harness health endpoints:

```http
GET /api/v1/health
GET /api/v1/health/harness
GET /api/v1/health/sources
GET /api/v1/health/providers
GET /api/v1/health/queue
GET /api/v1/health/cli
GET /api/v1/health/training
```

Expected health responses include a roll-up `status`, typed `checks`, and metrics for
skills, tools, GIS fixture sources, and training fixture videos.

Python MCP adapter fixture smoke:

```python
from plotlot.domain.types import ToolContext
from plotlot.harness import FullHarnessMCPAdapter
from plotlot.harness.full_harness_mcp import FullHarnessMCPToolCallRequest

adapter = FullHarnessMCPAdapter()
result = adapter.call_tool(
    FullHarnessMCPToolCallRequest(
        tool_name="search_municode",
        arguments={"jurisdiction": "miami", "query": "parking"},
        context=ToolContext(
            workspace_id="ws_fixture",
            actor_user_id="mcp_fixture",
            run_id="run_fixture_mcp",
        ),
    )
)
assert result.status == "completed"
```

Dedicated harness MCP server:

```bash
uv run plotlot-mcp
# or
uv run plotlot-harness-mcp
# legacy
uv run plotlot-legacy-mcp
```

API Municode fixture lane:

```http
POST /api/v1/municode/search
GET /api/v1/municode/sections/:sectionId
POST /api/v1/ordinances/extract-rules
```

Expected Municode responses include provider, jurisdiction, section identifier, source
URL, excerpt, `requires_official_verification` freshness, and extracted rules when
deterministically available.

API persisted residual land value calculation:

```http
POST /api/v1/deal-analysis/residual-land-value
Content-Type: application/json

{
  "run_id": "run_fixture_api_calc",
  "input": {
    "as_built_value": 1235000,
    "desired_profit": 150000,
    "hard_costs": 600000,
    "soft_costs": 90000,
    "contingency": 60000,
    "developer_fee": 30000,
    "closing_costs": 15000,
    "financing_costs": 40000,
    "holding_costs": 20000,
    "selling_costs": 35000,
    "asking_price": 175000
  }
}
```

Expected response includes `calculation_id`, `run_id`, `calculation_type`,
`inputs`, `outputs`, and `formula_version`. The same record is available at
`GET /api/v1/harness/runs/:runId/calculations` and
`GET /api/v1/calculations/:calculationId`.

## Verification

Commands run successfully:

```bash
uv run ruff check src/ tests/
uv run mypy src
uv run pytest tests/unit/ -q --tb=short
uv run pytest tests/unit/test_harness_calculation_store.py tests/unit/test_harness_cli.py tests/unit/test_harness_api.py -q
uv run pytest tests/unit/test_harness_underwriting_calculators.py tests/unit/test_harness_cli.py::test_cli_calc_residual_land_value_outputs_json -q
uv run pytest tests/unit/test_harness_cli.py tests/unit/test_harness_job_queue.py -q
uv run pytest tests/unit/test_harness_job_queue.py tests/unit/test_harness_api.py tests/unit/test_harness_cli.py -q
uv run pytest tests/unit/test_harness_run_store.py tests/unit/test_harness_api.py tests/unit/test_harness_cli.py -q
uv run pytest tests/unit/test_calculator.py tests/unit/test_harness_cli.py tests/unit/test_harness_api.py -q
uv run pytest tests/unit/test_harness_evidence_store.py tests/unit/test_harness_cli.py::test_cli_run_persists_fixture_evidence_for_inspection tests/unit/test_harness_api.py::test_harness_run_evidence_api_reads_persisted_fixture_evidence tests/unit/test_harness_job_queue.py -q
uv run pytest tests/unit/test_full_harness_contracts.py tests/unit/test_harness_report_store.py tests/unit/test_harness_cli.py tests/unit/test_harness_api.py tests/unit/test_harness_job_queue.py -q
uv run pytest tests/unit/test_full_harness_contracts.py tests/unit/test_harness_verification_store.py tests/unit/test_harness_report_store.py tests/unit/test_harness_evidence_store.py tests/unit/test_harness_cli.py tests/unit/test_harness_api.py tests/unit/test_harness_job_queue.py -q
uv run pytest tests/unit/test_harness_debug_bundle.py tests/unit/test_harness_run_store.py tests/unit/test_harness_cli.py tests/unit/test_harness_api.py tests/unit/test_harness_report_store.py tests/unit/test_harness_verification_store.py tests/unit/test_harness_evidence_store.py tests/unit/test_harness_calculation_store.py -q
uv run pytest tests/unit/test_harness_approval_store.py tests/unit/test_harness_approvals_cli.py tests/unit/test_harness_approvals_api.py -q --tb=short
uv run pytest tests/unit/test_harness_health.py -q --tb=short
uv run pytest tests/unit/test_harness_evals.py -q --tb=short
uv run pytest tests/unit/test_harness_codex_reference.py tests/unit/test_harness_codex_cli.py -q --tb=short
uv run pytest tests/unit/test_municode_source_lane.py tests/unit/test_harness_municode_cli.py tests/unit/test_harness_municode_api.py -q --tb=short
uv run pytest tests/unit/test_harness_memory_store.py tests/unit/test_harness_memory_cli.py tests/unit/test_harness_memory_api.py tests/unit/test_harness_health.py tests/unit/test_harness_debug_bundle.py -q --tb=short
uv run pytest tests/unit/test_full_harness_policy.py tests/unit/test_full_harness_registries.py tests/unit/test_harness_runtime.py tests/unit/test_agent_tool_policy.py -q --tb=short
uv run pytest tests/unit/test_harness_tool_router.py tests/unit/test_harness_tools_cli.py tests/unit/test_harness_api.py::test_harness_tool_inspect_and_call_api_use_shared_router tests/unit/test_harness_api.py::test_harness_tool_call_api_exposes_approval_required_status -q --tb=short
uv run pytest tests/unit/test_harness_mcp_parity.py tests/unit/test_harness_tool_router.py tests/unit/test_harness_tools_cli.py tests/unit/test_harness_api.py::test_harness_tool_inspect_and_call_api_use_shared_router tests/unit/test_harness_api.py::test_harness_tool_call_api_exposes_approval_required_status tests/unit/test_tools_api.py::test_tools_call_geocode_matches_mcp_adapter -q --tb=short
uv run pytest tests/unit/test_harness_mcp_server.py tests/unit/test_harness_mcp_parity.py -q --tb=short
uv run pytest tests/unit/test_harness_tool_call_store.py tests/unit/test_harness_run_store.py::test_local_store_appends_tool_events_with_run_sequence tests/unit/test_harness_tools_cli.py::test_cli_tools_call_persists_tool_call_and_appends_run_events tests/unit/test_harness_api.py::test_harness_tool_call_api_persists_tool_call_and_appends_events tests/unit/test_harness_debug_bundle.py::test_debug_bundle_exports_run_traceability_without_transcript_text -q --tb=short
uv run pytest tests/unit/test_harness_run_store.py::test_local_store_cancels_queued_run_with_ordered_event tests/unit/test_harness_run_store.py::test_local_store_rejects_completed_run_cancellation tests/unit/test_harness_cli.py::test_cli_runs_cancel_updates_queued_run_and_emits_event tests/unit/test_harness_api_cancellation.py::test_harness_run_cancel_api_updates_queued_run_and_emits_event -q --tb=short
uv run pytest tests/unit/test_harness_job_cancellation.py -q --tb=short
uv run pytest tests/unit/test_harness_job_queue.py tests/unit/test_harness_job_failure_cli.py -q --tb=short
uv run pytest tests/unit/test_harness_report_export.py -q --tb=short
uv run pytest tests/unit/test_harness_scaffold.py tests/unit/test_harness_scaffold_cli.py tests/unit/test_full_harness_contracts.py::test_scaffold_manifest_contract_preserves_generated_file_statuses tests/unit/test_harness_cli.py::test_cli_help_lists_harness_commands -q --tb=short
uv run pytest tests/unit/test_harness_tui.py -q --tb=short
uv run plotlot training discover --url 'https://www.youtube.com/watch?v=0IS1iFMJ8sQ' --json
uv run plotlot doctor
uv run plotlot eval suites
uv run plotlot eval run
uv run plotlot codex goal generate
uv run plotlot codex doctor
uv run plotlot municode search --jurisdiction miami --query parking
uv run plotlot municode extract-rules --section-id municode_miami_parking_fixture
uv run plotlot run acquisition-memo --address "example Miami-Dade fixture address" --source-mode fixture --assumption avgUnitSizeSf=850 --assumption efficiencyFactor=0.85 --assumption targetProfitPct=0.18 --stream
uv run plotlot evidence list --run-id <run-id>
uv run plotlot evidence show <evidence-id>
uv run plotlot claims list --run-id <run-id>
uv run plotlot claims show <claim-id>
uv run plotlot reports show <report-id>
uv run plotlot verification show --report-id <report-id>
uv run plotlot runs export-debug-bundle <run-id>
uv run plotlot approvals request --run-id <run-id> --action export_lender_package --risk-level high --reason "Export requires analyst approval."
uv run plotlot approvals list --run-id <run-id>
uv run plotlot approvals approve <approval-id> --resolved-by analyst@example.test
uv run plotlot tui --screen approvals --run-id <run-id> --json
uv run plotlot tui --screen approvals --approve <approval-id> --resolved-by analyst@example.test --json
uv run plotlot tui --screen replay-debug --run-id <run-id> --json
uv run plotlot memory write --workspace-id ws_fixture --memory-type site_assumption --content "Use 850 sf units." --source-run-id <run-id> --evidence-id <evidence-id>
uv run plotlot memory list --workspace-id ws_fixture
uv run plotlot memory show <memory-id>
uv run plotlot tools inspect search_municode
uv run plotlot tools call search_municode --run-id <run-id> --workspace-id ws_fixture --json '{"jurisdiction":"miami","query":"parking"}'
uv run plotlot tools calls --run-id <run-id>
uv run plotlot reports finalize <report-id>
uv run plotlot jobs create --address "example Miami-Dade fixture address" --analysis-type acquisition-memo --source-mode fixture --idempotency-key cli-split-smoke
uv run plotlot jobs run-next
uv run plotlot jobs events <job-id>
uv run plotlot calc residual-land-value --json '{"as_built_value":1235000,"desired_profit":150000,"hard_costs":600000,"soft_costs":90000,"contingency":60000,"developer_fee":30000,"closing_costs":15000,"financing_costs":40000,"holding_costs":20000,"selling_costs":35000,"asking_price":175000}'
uv run plotlot calc residual-land-value --run-id run_fixture_cli_calc --json '{"as_built_value":1235000,"desired_profit":150000,"hard_costs":600000,"soft_costs":90000,"contingency":60000,"developer_fee":30000,"closing_costs":15000,"financing_costs":40000,"holding_costs":20000,"selling_costs":35000,"asking_price":175000}'
uv run plotlot calculations list --run-id run_fixture_cli_calc
uv run plotlot scaffold tool demo_tool --root <temp-dir>
uv run plotlot tui --screen run-monitor --run-id <run-id> --json
uv run plotlot tui --screen replay-debug --run-id <run-id> --json
```

## Remaining Full-Harness Work

- `src/plotlot/harness/`: replace local JSON fixture persistence with database-backed run,
  event, evidence, claim, calculation, report, approval, memory, training, and usage stores for
  production deployment. Evidence, claim/report, verification, calculation, and approval
  ledger persistence now exist locally but still need DB-backed tenancy, authorization,
  retention, richer claim linking, and production-grade verifier profile integration.
- `src/plotlot/harness/`: connect local approval artifacts to policy pause/resume, richer verifier profiles,
  explicit memory use in context compilation, and model gateway. The current queue is
  local JSON-backed and single-worker only; production still needs
  database or broker-backed leases, retries, dead letters, active worker interruption,
  and concurrency control.
- `src/plotlot/harness/tool_call_store.py` and `src/plotlot/harness/run_store.py`: local
  tool-call persistence and run-event append now exist for CLI/API calls; production still
  needs database-backed tenancy, authorization checks, indexing, and transactional event
  appends.
- `src/plotlot/harness/south_florida_gis.py`: add live ArcGIS REST clients behind
  environment-gated adapters; keep fixture tests network-free.
- `src/plotlot/harness/municode_source.py`: add environment-gated live Municode/local
  ordinance adapters and raw source artifact persistence. Fixture mode now exists, but
  live mode intentionally fails closed.
- `src/plotlot/api/chat.py` and related retrieval/web lookup paths: shared bridges now
  exist for Municode fixtures, South Florida GIS fixture search, training-source
  discovery, `web_search`, property lookup, and local indexed ordinance search via the
  default harness runtime. Web lookup/chat-agent parity is now the active remaining
  task, with `web_search`, `search_zoning_ordinance`, and `lookup_property_info`
  already routed through the shared runtime. Remaining parity work is to migrate more
  legacy chat-only deterministic calculation/report actions onto shared harness
  execution without losing the current live-data behavior.
- `src/plotlot/api/harness.py`, `src/plotlot/api/harness_calculations.py`,
  `src/plotlot/api/harness_evidence.py`, `src/plotlot/api/harness_jobs.py`, and
  `src/plotlot/api/harness_reports.py`:
  persist runs, calculations, fixture evidence, fixture claims, fixture reports, and
  local report exports, local run cancellation, and local job cancellation. Production
  still needs DB-backed authorization, leases, and cancellation propagation to active
  workers/providers.
- `src/plotlot/harness/tui*.py` and `src/plotlot/cli_harness_tui.py`: expand from the
  current terminal workbench shell into richer keyboard navigation and deeper replay
  diagnostics. The current TUI reads shared stores/catalogs, can resolve approvals, and
  can render replay/debug summaries, but is not yet a full-screen Textual application.
- Frontend workbench remains to be connected to the new harness routes and event stream.
- Full-harness MCP adapter and dedicated server parity now exist; remaining work is
  deciding whether to replace or augment the legacy default `plotlot-mcp` server in
  production deployments while preserving the `HarnessToolRouter`, policy, source
  catalog, ledgers, and verifier as the only business-logic path.
- `src/plotlot/storage/models.py` and `src/plotlot/pipeline/calculator.py` are legacy
  oversized modules; future PRs should split ORM domains and calculator families before
  adding more behavior there.
