# PlotLot Full Harness Goal

Build PlotLot as a workspace-native, event-driven, source-grounded real estate
development analyst harness.

## Operating Rules

- Preserve existing repo structure and working behavior.
- Use shared contracts, registries, policies, source catalog, evidence ledger,
  calculators, verifier, report generator, CLI, API, worker, TUI, and frontend surfaces.
- Do not create parallel business logic in separate surfaces.
- Do not let model output invent zoning rules, GIS facts, financial assumptions, costs,
  transcripts, citations, or jurisdiction facts.
- Every material claim must link to evidence, deterministic calculation, explicit user
  assumption, or permitted training concept.
- Treat fixture and mock source modes as preliminary, never production evidence.
- Keep protected or paywalled training content out of automated download/transcription.
- Current scope excludes production private transcript storage, user-upload media
  workflows, and final lender-grade packages from live verified sources.

## Source Lanes

- Municode Florida ordinance sections with official-verification caveats.
- South Florida GIS source lane with Miami-Dade and Broward adapters under one shared
  provider interface.
- Training source lane for public RehabValuator-style pages, public video metadata,
  permitted captions, concept extraction, workflow mappings, and searchable structured
  knowledge.
- Optional Codex CLI reference lane for developer/operator workflows only, not production
  runtime dependency.

## Deliverables

- Durable `AnalysisRun` state machine and ordered event log.
- Queue/worker abstraction and local synchronous execution path.
- Skill, role, tool, plugin, source, policy, verifier, report, model, memory, scaffold,
  eval, and replay registries.
- Deterministic feasibility, underwriting, ARV/comps, residual land value, BRRRR,
  construction budget, draw schedule, and sensitivity calculators.
- CLI, API, TUI, frontend workbench, and MCP parity surfaces using the same runtime.
- Existing web lookup and chat-agent tools must route shared harness tools through the
  same `HarnessToolRouter`, policy engine, source catalog, evidence behavior, and event
  trace wherever a matching harness tool exists.
- Fixture and environment-gated integration tests for source adapters.
- Evals for harness, evidence, South Florida GIS, underwriting, CLI, and training
  ingestion workflows.

## Acceptance Checks

- `uv run ruff check src/ tests/`
- `uv run mypy src`
- `uv run pytest tests/unit/ -q --tb=short`
- Fixture CLI acquisition memo run emits ordered events and preliminary report metadata.
- `plotlot runs events <run-id>` and `plotlot runs replay <run-id>` read the saved run
  timeline from the shared harness store.
- `plotlot jobs create ...`, `plotlot jobs run-next`, and `plotlot jobs events <job-id>`
  exercise the queued local worker path and persist the resulting run through the same
  harness store.
- Fixture Broward zoning research keeps BMSD zoning contextual for municipal sites.
- Fixture YouTube ARV/comps/offer source maps to ARV/comparable-sales/offer workflow.
- Reports cannot finalize when verification blocks or mock/fixture evidence is treated
  as production evidence.
- Existing chat/web lookup tools expose matching full-harness tools and execute them
  through `HarnessToolRouter` instead of duplicating source-lane logic.
