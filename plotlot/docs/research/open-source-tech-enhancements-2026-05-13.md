# Open Source Tech Research for PlotLot

Research date: 2026-05-13

## Context

PlotLot is already a credible AI-assisted land feasibility app:

- Next.js 16 / React 19 frontend with lookup and agent modes.
- FastAPI / Python 3.12 backend.
- Neon PostgreSQL plus `pgvector` for ordinance chunks and hybrid retrieval.
- ArcGIS / county provider layer for parcel facts.
- LLM extraction plus deterministic density calculation.
- Current product direction: durable agent memory, source-backed trust, ingestion governance, broader coverage, and stronger evals.

Local evidence:

- `docs/PLOTLOT_FLOW_CONTRACT.md` says agent memory and recall are intended durable behaviors, but durable backend memory is still planned.
- `docs/PLOTLOT_TECHNICAL_OVERVIEW.md` describes the current stack and notes 8,142 ordinance chunks, 17 municipalities, and 88 discoverable via Municode.
- `src/plotlot/api/chat.py` still uses a bounded in-memory `SessionStore` for chat memory.
- `src/plotlot/storage/models.py` already contains workspace/project/site/analysis/evidence/tool-run/report/document models, so the repo has the right persistence direction.
- `src/plotlot/retrieval/search.py` already uses hybrid `pgvector` plus PostgreSQL full-text search with RRF.

## Executive Recommendation

The best open-source additions are not more frontend polish or another generic chatbot framework. The highest leverage is infrastructure that makes PlotLot more trustworthy, durable, and operationally scalable:

1. **PostGIS** for first-class geospatial storage, spatial joins, coverage checks, and comp queries.
2. **Pydantic AI** as the typed agent/tool adapter inside the existing harness, with **LangGraph** reserved for resumable multi-step agent workflows if checkpointing becomes the core requirement.
3. **Phoenix or Langfuse** for LLM traces, retrieval/tool observability, prompt iteration, and eval feedback loops.
4. **Promptfoo** for CI-friendly prompt, RAG, and agent regression tests.
5. **Dagster** for ordinance/open-data ingestion assets, freshness, lineage, and batch municipality expansion.
6. **Docling** for robust ordinance PDF / DOCX / scanned document conversion before chunking.
7. **Temporal** only for critical, long-running user-facing workflows that must survive crashes and resume exactly.
8. **Valkey** for durable-ish low-latency session/cache/queue primitives, not as the source of truth.
9. **MapLibre GL JS** for a future map modernization path when vector tiles, 3D parcels, or heavier spatial visualization become a product priority.

## Ranked Options

### 1. PostGIS

Fit: very high  
Effort: medium  
Risk: low to medium  
Recommendation: adopt first

PlotLot currently stores geometries as JSON and performs many geospatial operations through ArcGIS APIs, Shapely, or client-side map components. PostGIS should become the canonical internal spatial layer for persisted parcels, sites, boundaries, open-data coverage, comps, flood/wetlands overlays, and distance queries.

Why it matters:

- Enables indexed spatial joins: parcel intersects zoning district, site within municipality, comp within radius, boundary coverage validation.
- Keeps geospatial truth close to the existing PostgreSQL data model instead of spreading it across ArcGIS responses, JSON blobs, and frontend map state.
- Supports better auditability: store the geometry, source URL, retrieval timestamp, and content hash together.
- Improves comps and coverage queries without requiring repeated live ArcGIS calls.

How it fits the repo:

- Add PostGIS extension to migrations.
- Add geometry columns to `sites`, `connector_datasets`, or new normalized parcel/zoning-boundary tables.
- Keep `pgvector` for ordinance text. Use PostGIS for spatial truth. These are complementary.
- Start with `ST_GeomFromGeoJSON`, `ST_Intersects`, `ST_DWithin`, GiST indexes, and source metadata.

Watchouts:

- Neon/Postgres plan must support PostGIS.
- Do not migrate all historical JSON geometry immediately. Add a new normalized path and dual-write new results first.

Sources:

- PostGIS docs: https://postgis.net/docs/
- Spatial query/index guidance: https://www.postgis.net/docs/manual-3.2/using_postgis_query.html
- Spatial index FAQ: https://postgis.net/documentation/faq/spatial-indexes/

### 2. Pydantic AI

Fit: high  
Effort: medium  
Risk: medium  
Recommendation: use as an adapter, not as a wholesale app rewrite

PlotLot already uses Pydantic v2, FastAPI, typed tool contracts, and Pydantic-style schemas. Pydantic AI is a natural fit for converting the current bespoke LLM/tool loop into a more strongly typed, model-agnostic agent layer.

Why it matters:

- Strong typed outputs and tool contracts are core to a trust-critical zoning product.
- Model-agnostic support fits PlotLot's current multi-provider LLM strategy.
- OpenTelemetry compatibility lines up with the repo's existing tracing direction.
- The framework can sit behind the current `HarnessRuntime` and `ToolPolicy` instead of replacing governance.

How it fits the repo:

- Start with one narrow agent path: agent chat property/zoning lookup.
- Map existing `CHAT_TOOLS` / `tool_registry.py` contracts into Pydantic AI tools.
- Preserve existing approval policy and evidence persistence.
- Evaluate typed output retries against `ZoningReportResponse` and `EvidenceBackedReportSection`.

Watchouts:

- Avoid duplicating policy in the framework. Tool authorization must remain in PlotLot's harness.
- Do not let a framework abstraction bury source/evidence IDs.

Sources:

- Pydantic AI overview: https://pydantic.dev/docs/ai/overview/
- Pydantic AI agents: https://pydantic.dev/docs/ai/core-concepts/agent/

### 3. LangGraph

Fit: high for durable workflows, medium for simple chat  
Effort: medium to high  
Risk: medium  
Recommendation: adopt only where checkpointing/resume is the product requirement

LangGraph's strongest fit is durable multi-step agent workflows with checkpointing, memory stores, human-in-the-loop interrupts, and resume. PlotLot has several candidates: agent research sessions, document-generation flows, evidence review/approval, and multi-step deal analysis.

Why it matters:

- Current chat memory is in-process and TTL-bound.
- The product contract wants durable agent memory and cross-session recall.
- Existing approval models and `HarnessRuntime` are already close to a graph-like execution model.

How it fits the repo:

- Do not start by rewriting `/api/v1/chat`.
- First model one workflow as a graph: `geocode -> property -> ordinance search -> extraction -> evidence report -> approval/document`.
- Use a Postgres checkpointer/store if adopted; avoid in-memory persistence except for tests.
- Stream graph node events to the frontend so users can see background work.

Watchouts:

- LangGraph checkpoints can store a lot of state; keep large artifacts in PlotLot tables/object storage and checkpoint references only.
- The repo already has a harness. LangGraph should orchestrate steps, not bypass policy.

Sources:

- LangGraph persistence/memory docs: https://docs.langchain.com/oss/python/langgraph/persistence
- LangGraph checkpoints reference: https://reference.langchain.com/python/langgraph/checkpoints/

### 4. Phoenix or Langfuse

Fit: high  
Effort: low to medium  
Risk: low  
Recommendation: choose one observability/eval platform; do not run both long term

PlotLot already logs some MLflow spans and model cost metrics. That is useful, but LLM apps also need visibility into prompts, model calls, retrieval chunks, tool decisions, latency, failures, and human/eval labels.

Phoenix strengths:

- Open-source AI observability and evaluation.
- Built on OpenTelemetry/OpenInference.
- Good fit for traces that include model calls, retrieval, tool use, and custom logic.
- Can accept OTLP traces, which matches a vendor-neutral instrumentation direction.

Langfuse strengths:

- Open-source, self-hostable LLM engineering platform.
- Strong prompt management, tracing, datasets, evals, and analytics.
- Broad integrations.

Recommendation for PlotLot:

- Prefer **Phoenix** if the priority is OTel-native tracing and evals close to existing Python retrieval/tool spans.
- Prefer **Langfuse** if the priority is prompt management, dataset UI, and productized LLM analytics.
- Keep MLflow only if it remains useful for model experiment tracking; otherwise avoid split-brain tracing.

Sources:

- Phoenix docs: https://arize.com/docs/phoenix
- Phoenix GitHub: https://github.com/Arize-ai/phoenix
- Langfuse docs: https://langfuse.com/docs/
- Langfuse self-hosting: https://langfuse.com/self-hosting
- Langfuse GitHub: https://github.com/langfuse/langfuse

### 5. Promptfoo

Fit: high  
Effort: low  
Risk: low  
Recommendation: add to CI after the first gold-set cases are stable

PlotLot's correctness depends on prompts, RAG retrieval, agent tool choices, and refusal/uncertainty behavior. Promptfoo is a practical way to run repeatable LLM regression checks in CI without building a custom eval runner first.

Why it matters:

- The repo already has `GoldSetCase`, `EvalRun`, and eval-oriented tests.
- Promptfoo can test prompts, agents, RAGs, and red-team cases through declarative configs.
- It is language-agnostic and can hit local HTTP endpoints.

How it fits the repo:

- Add a small `promptfooconfig.yaml` for 10 to 20 canonical zoning questions.
- Run against local `/api/v1/chat` and `/api/v1/analyze`.
- Assert citation presence, "I don't know" behavior, no unsupported legal/financial advice, and correct tool routing.
- Store summary output as CI artifacts before wiring it into a quality gate.

Watchouts:

- LLM evals can be flaky. Gate deterministic assertions first; use judge-based scores as advisory until stable.

Sources:

- Promptfoo docs: https://www.promptfoo.dev/docs/intro/
- Promptfoo GitHub: https://github.com/promptfoo/promptfoo

### 6. Dagster

Fit: high  
Effort: medium  
Risk: low to medium  
Recommendation: finish the existing Dagster lane for ingestion and data-quality assets

The repo already has a `dagster/pyproject.toml`, so this may be partly started. Dagster is a good fit for source ingestion, chunking, embedding, freshness checks, county coverage, and data-quality dashboards.

Why it matters:

- Ordinance ingestion is not a simple request/response concern.
- Municipality expansion needs lineage, freshness, backfills, retries, and failure visibility.
- PlotLot's trust layer improves when every chunk has source URL, scrape time, embedding model, and freshness status.

How it fits the repo:

- Model each municipality ordinance corpus as a Dagster asset.
- Model each ArcGIS connector dataset as a discoverable asset with freshness metadata.
- Add assets for `ordinance_chunks`, `connector_datasets`, and `gold_set_cases`.
- Materialize embeddings and quality stats as explicit downstream assets.

Watchouts:

- Dagster is heavier than a simple queue. Use it for data assets and scheduled ingestion, not every user request.

Sources:

- Dagster docs: https://docs.dagster.io/
- Dagster GitHub: https://github.com/dagster-io/dagster
- Software-defined assets docs: https://release-1-8-1.dagster.dagster-docs.io/concepts/assets/software-defined-assets

### 7. Docling

Fit: high  
Effort: medium  
Risk: medium  
Recommendation: pilot on difficult ordinance PDFs before broad adoption

Municipal code sources are not always clean HTML. Some cities publish PDFs, scanned PDFs, tables, amendments, agendas, and DOCX files. Docling can improve the ingest pipeline before chunking and embedding.

Why it matters:

- Better document structure means better chunks.
- Tables and layout matter for setbacks, parking ratios, lot dimensions, use matrices, and definitions.
- It can reduce fragile scraper-specific parsing logic.

How it fits the repo:

- Add a `DocumentConverter` path for non-HTML ordinance sources.
- Preserve page/section/table metadata into chunk lineage.
- Compare retrieval/eval results against the current BeautifulSoup pipeline before switching.

Watchouts:

- OCR/layout models increase compute needs.
- Keep a deterministic conversion cache keyed by source URL and content hash.

Sources:

- IBM Research Docling paper page: https://research.ibm.com/publications/docling-an-efficient-open-source-toolkit-for-ai-driven-document-conversion
- Docling technical report: https://arxiv.org/abs/2408.09869

### 8. Temporal

Fit: medium to high  
Effort: high  
Risk: medium  
Recommendation: defer until workflows need strict crash-proof resume semantics

Temporal is more than a queue. It is useful when a workflow must survive process crashes, retries, outages, human delays, and long wait states. That is valuable, but operationally heavier than a first-pass background worker.

Best PlotLot use cases:

- Long-running ingestion batches across municipalities.
- Multi-step deal package generation with approvals.
- Paid-user report generation where failure/retry semantics matter.
- External connector syncs where idempotency and auditability are required.

Recommendation:

- Use Dagster for data assets first.
- Use Temporal when user-facing workflows need exact resume and durable execution guarantees.

Sources:

- Temporal docs: https://docs.temporal.io/
- Temporal Python SDK: https://python.temporal.io/
- Temporal Python SDK GitHub: https://github.com/temporalio/sdk-python

### 9. Valkey

Fit: medium  
Effort: low to medium  
Risk: low  
Recommendation: use for cache/session/ephemeral state, not source-of-truth memory

Valkey is the Linux Foundation-backed open-source continuation/fork of Redis. It is a good fit for shared cache, rate limits, session coordination, websocket/SSE fanout, and low-latency ephemeral state.

How it fits the repo:

- Replace in-process `_sessions` with a shared store so multiple backend instances can preserve short-lived session state.
- Use it for rate limiting and request deduplication.
- Use streams or lists for lightweight background work only if reliability requirements stay modest.

Watchouts:

- Durable agent memory should go into PostgreSQL models, not Valkey alone.
- If task correctness matters after crashes, use Temporal or a proper persistent job architecture.

Sources:

- Valkey introduction: https://valkey.io/topics/introduction/
- Valkey project: https://valkey.io/

### 10. MapLibre GL JS

Fit: medium  
Effort: medium to high  
Risk: medium  
Recommendation: defer until map UX/performance becomes a bottleneck

PlotLot already uses Leaflet/ESRI Leaflet and Google Maps. MapLibre GL JS becomes attractive when the app needs heavier vector tiles, data-driven styling, 3D terrain/buildings, or high-performance client-side parcel/zoning visualization.

How it fits the repo:

- Keep existing Leaflet maps for now.
- Pilot MapLibre in a single `ParcelViewer` variant only after PostGIS/vector tile strategy is clear.
- Pair with a vector tile server such as Martin or Tegola if serving internal parcel/zoning layers.

Sources:

- MapLibre GL JS project page: https://maplibre.org/projects/gl-js/
- MapLibre GL JS docs: https://maplibre.org/maplibre-gl-js/docs/

## Suggested Adoption Sequence

### Phase 1: Trust and Spatial Foundation

Deliverables:

- Add PostGIS migration and one normalized spatial table.
- Persist new parcel/site geometries with source metadata.
- Add spatial coverage checks and a few `ST_DWithin` / `ST_Intersects` queries.
- Add Promptfoo smoke evals for citation and unsupported-claim behavior.

Why first:

- It strengthens the factual layer before making the agent more ambitious.
- It uses the database already in the stack.

### Phase 2: Agent Durability and Observability

Deliverables:

- Choose Phoenix or Langfuse.
- Instrument chat/analyze paths for model calls, retrieval chunks, tool calls, approval decisions, and costs.
- Move session memory from in-process storage to PostgreSQL-backed durable models.
- Pilot Pydantic AI for one typed agent path.

Why second:

- Once traces and evals exist, framework changes become measurable instead of subjective.

### Phase 3: Ingestion and Coverage Expansion

Deliverables:

- Convert the existing Dagster lane into production assets for ordinance ingestion.
- Add freshness and lineage metadata for ordinance chunks and connector datasets.
- Pilot Docling on PDF/DOCX/scanned ordinance sources.
- Tie ingestion runs to gold-set cases and eval runs.

Why third:

- Broader coverage without provenance and evals creates trust debt.

### Phase 4: Durable Workflow Runtime

Deliverables:

- Choose LangGraph for resumable agent graphs or Temporal for durable user-facing workflows.
- Keep the existing `HarnessRuntime` as the policy/evidence boundary.
- Stream workflow state to the frontend as user-readable progress.
- Store large artifacts in PlotLot tables/object storage, not checkpoints.

Why last:

- These systems are powerful but bring architectural gravity. Adopt after the evidence and data layers are ready.

## Things I Would Not Do Yet

- Do not replace `pgvector` with Qdrant/Weaviate/Pinecone right now. The current hybrid PostgreSQL approach is aligned with the repo and easier to audit. Revisit only if vector scale or latency becomes a measured bottleneck.
- Do not replace Clerk or Stripe for "open-source purity." They are not the limiting factor for the current product direction.
- Do not move all agent behavior into a framework before tracing/evals exist.
- Do not make Valkey the durable memory store. Use PostgreSQL for durable user/report/evidence memory.
- Do not modernize maps before the spatial data model is fixed.

## Near-Term PR Candidates

1. `postgis-spatial-foundation`: migration, geometry column/table, spatial helper functions, and tests.
2. `llm-tracing-eval-foundation`: Phoenix or Langfuse instrumentation plus Promptfoo smoke config.
3. `durable-agent-memory`: persist chat sessions/messages to existing workspace/project/site models.
4. `dagster-ordinance-assets`: define municipality ordinance assets and freshness metadata.
5. `docling-ingest-pilot`: convert 3 to 5 hard ordinance PDFs into structured chunks and compare retrieval quality.

## Final Ranking

| Rank | Tech | Primary value | Adopt now? |
| --- | --- | --- | --- |
| 1 | PostGIS | Spatial truth, comps, overlays, coverage | Yes |
| 2 | Phoenix or Langfuse | LLM/tool/retrieval observability | Yes |
| 3 | Promptfoo | CI evals and red-team checks | Yes |
| 4 | Pydantic AI | Typed agent adapter | Pilot |
| 5 | Dagster | Ingestion lineage/freshness | Pilot/finish existing lane |
| 6 | Docling | Better ordinance document ingestion | Pilot |
| 7 | LangGraph | Durable/resumable agent graphs | Later pilot |
| 8 | Temporal | Crash-proof long workflows | Later, when needed |
| 9 | Valkey | Shared ephemeral cache/session/rate limit | Opportunistic |
| 10 | MapLibre GL JS | Advanced map rendering | Defer |
