# PlotLot De-Slop and Evaluation Architecture

**Date:** 2026-09-01  
**Base:** `cpt-pro@a3531aed37b6d7186addc1ef3b8ee00ec5199778`  
**Work branch:** `feat/cpt-pro-deslop`

## Objective

Reduce PlotLot to one understandable product architecture while preserving the working multi-agent harness. The cleanup must not conceal existing failures, invent market coverage, weaken approval controls, or make the LLM responsible for deterministic zoning, comparable-sale, or underwriting calculations.

The approved program has eight deliverables:

1. Establish and record the real operational and test baseline.
2. Work in an isolated branch based on `cpt-pro`.
3. Add characterization and architecture tests before moving behavior.
4. Remove tracked AI workspace state, stale personal instructions, and disconnected scaffolding.
5. Introduce one analysis application service for JSON, SSE, chat, MCP, and agent tools.
6. Introduce one governed tool-execution transaction for all transports.
7. Add reliable comparable-sale qualification and conservative acquisition decision support.
8. Convert property leads from Google Drive into a sanitized, repeatable evaluation corpus.

## Current Baseline

### Known green lanes on `cpt-pro`

- repository hygiene
- Ruff lint and formatting
- mypy
- backend unit tests with Postgres
- frontend lint, build, and UI tests
- Playwright no-DB

### Known failing lanes

- DB-backed Playwright: the lookup report scenario receives an unexpected HTTP 503 after migrations and backend health succeed.
- Nightly provider health on `main`: Hub discovery rejects Miami-Dade, Broward, and Palm Beach candidates; Broward legacy lookup also times out.
- Deployed API health on `main`: the Render health endpoint does not return within the current 15-second single-attempt probe.

These are baseline defects. Cleanup work may fix them, but must not relabel, skip, or suppress them.

## Architectural Decision

Use an incremental strangler migration, not a rewrite.

```text
HTTP JSON / SSE / Chat / MCP / CLI / Multi-agent coordinator
                            |
                            v
                    Application services
               AnalysisService / ToolExecutor
                            |
                            v
                 Domain rules and deterministic tools
                            |
                            v
             Provider ports / repositories / integrations
```

Transport modules may authenticate, validate transport envelopes, and render results. They may not independently orchestrate geocoding, property lookup, ordinance retrieval, approvals, evidence persistence, calculations, or report generation.

## Canonical Analysis Service

Introduce a transport-neutral analysis application service.

```python
class AnalysisService:
    async def analyze(
        self,
        request: AnalysisRequest,
        *,
        emit: AnalysisEventSink | None = None,
    ) -> AnalysisResult: ...
```

Requirements:

- One execution path for synchronous JSON and streamed SSE analysis.
- Structured events emitted by the service; SSE only serializes them.
- Existing deterministic provider, ordinance, LLM interpretation, calculation, comps, and pro-forma components are reused.
- No API route imports underscore-prefixed pipeline functions.
- Partial coverage and timeouts become explicit typed outcomes.
- The current `lookup_address()` function remains a compatibility adapter until all call sites migrate.

## Canonical Tool Executor

`HarnessRuntime` remains the low-level policy/handler runtime. Add one application-level `ToolExecutor` transaction around it to own:

1. canonical contract lookup and argument validation
2. workspace/project/site context resolution
3. durable approval validation
4. governed runtime call
5. tool-run persistence
6. evidence validation and persistence
7. artifact/report/document persistence
8. audit events
9. commit or rollback
10. canonical transport-neutral result mapping

REST tools, chat, HTTP MCP, FastMCP, and multi-agent execution must call this executor instead of duplicating approval and persistence behavior.

## Reliable Comparable Sales

Add a dedicated deterministic comps capability.

A candidate sale is rejected when it is:

- the subject property
- duplicated
- missing source provenance
- outside maximum age
- outside maximum radius
- incompatible by property or land-use type
- materially incompatible by lot or building size
- a statistical price outlier without corroboration

Valuation is withheld unless at least three qualified sales remain. Confidence depends on count, freshness, distance, property similarity, and source diversity. The model may explain the result but may not select excluded sales or invent a value.

The acquisition decision basis is the lower of:

- qualified comparable-sale range floor
- deterministic residual land-value ceiling

Possible decisions are `advance_for_review`, `hold_for_inputs`, `reject_buy_box`, and `insufficient_evidence`. No result is an autonomous purchase instruction.

## Google Drive Evaluation Corpus

Drive data is treated as private source material, not application runtime state.

The ingestion workflow must:

- discover explicitly selected spreadsheet files
- extract only property-level fields needed for evaluation
- remove owner phone, owner email, mailing address, and free-text contact notes
- normalize and deduplicate addresses
- create a versioned JSON fixture under `plotlot/tests/fixtures/leads/`
- record source file identifiers and extraction timestamp in a manifest without copying contact data
- run the same workflow cases through the harness
- produce machine-readable metrics for parcel resolution, zoning evidence, comps qualification, residual value, decision status, latency, and abstention quality

The fixture must never be generated implicitly during normal unit tests. Refresh is an explicit authenticated command; CI consumes the committed sanitized fixture.

## Repository Scaffolding Policy

Remove from the product tree:

- `.claude/`
- `.omo/`
- `plotlot/.omx/`
- root `CLAUDE.md`
- nested `plotlot/CLAUDE.md`
- `GEMINI.md`
- personal prospect, identity, or outreach instructions
- generated agent execution evidence used as source code

Retain one neutral root `AGENTS.md`. Deterministic fixtures required by tests move to `plotlot/tests/fixtures/`. Repository hygiene must fail if removed workspace-state directories or personal-context files return.

Dagster/dbt are not deleted in this first cleanup commit. They are quarantined by documentation as non-runtime analytics tooling until active ownership and deployment are verified; destructive removal requires a separate evidence-backed decision.

## Provider Health

Health checks distinguish three conditions:

- application unavailable
- provider unavailable or timed out
- discovery candidate rejected by quality validation

The deployed API probe uses bounded retries with per-attempt evidence. Provider tests log candidate URLs, validation scores, and rejection reasons. A live provider outage does not cause deterministic unit-test failure, but the nightly health workflow must remain red and actionable.

## Testing Strategy

### Characterization

- Sync and streamed analysis share the same final report for an injected deterministic pipeline.
- All transports return equivalent policy outcomes for the same tool and context.
- Approval IDs are validated once through the canonical executor.
- Evidence identifiers survive tool execution and reporting.
- Multi-agent plans preserve current specialist boundaries.

### Architecture

AST/import tests prohibit:

- API routes importing underscore-prefixed pipeline helpers
- chat/MCP directly invoking canonical tool handlers
- domain modules importing API or storage transports
- tracked `.claude`, `.omo`, or `.omx` paths
- a second analysis orchestrator

### Comps and decisions

- duplicate, subject, stale, distant, incompatible, and outlier sales are excluded
- fewer than three qualified sales abstains
- conservative basis uses the lower supported value
- missing price or residual inputs never becomes a recommendation

### Evaluation

- sanitized fixture contains no email, phone, or mailing-contact fields
- each fixture row has a normalized address and stable case ID
- benchmark output records evidence and abstention behavior

## Error Handling

Canonical application errors:

- `bad_input`
- `not_found`
- `unsupported_market`
- `coverage_gap`
- `provider_timeout`
- `provider_unavailable`
- `approval_required`
- `policy_denied`
- `budget_exceeded`
- `insufficient_evidence`
- `internal_error`

No unavailable source is replaced with an unlabeled model estimate.

## Non-goals

- microservices
- rewriting county adapters
- replacing PostgreSQL or the existing job queue
- autonomous external outreach
- deleting analytics projects without ownership evidence
- UI redesign in the same cleanup slice
- claiming uniform nationwide zoning or comps coverage

## Definition of Done

1. Baseline failures are documented with reproducible commands and root-cause evidence.
2. The cleanup branch contains no tracked AI workspace state or personal tool instructions.
3. One analysis service powers JSON and SSE; compatibility adapters preserve callers.
4. One governed tool executor owns approvals, persistence, evidence, and artifacts across transports.
5. Reliable comps abstain when evidence is weak and feed a conservative decision packet.
6. A sanitized Drive-derived lead fixture and repeatable benchmark exist.
7. Full backend, frontend, Playwright, provider-health, and release gates have explicit terminal results.
8. No cleanup commit is merged into `main` without green required checks and review.
