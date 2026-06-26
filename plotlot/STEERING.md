# STEERING.md — Human-injected critical work

Ralph reads this file BEFORE selecting a task from IMPLEMENTATION_PLAN.md.
Items here PREEMPT the plan. Complete them first, remove when done, then proceed
to the plan. This is the "tune reactively" mechanism — when Ralph goes off track
or a critical issue surfaces mid-loop, add it here instead of interrupting.

Format: one item per `- [ ]` bullet, newest at top. Remove the bullet when done.

## Pending critical work

(none currently — Ralph proceeds to IMPLEMENTATION_PLAN.md)

<!-- Example entries:
- [ ] comps_sources: reconcile Broward registry fields against live schema (the metadata listing diverged once; verify before trusting)
- [ ] before any "comps work" claim, run tests/integration/test_comps_south_fl_live.py with PLOTLOT_LIVE_TESTS=1
-->

- [x] RESOLVED 2026-06-26: Dimensional standard values must be verified against
      the ingested ordinance_chunks corpus (read chunk_text) before claiming
      source_section_id. Hand-entered guesses tagged with a section name are a
      claim-without-evidence failure. Miami/Hollywood rows are STAGED until
      their corpora are ingested (Phase 9).

- [ ] CRITICAL 2026-06-26: Corpus-driven extraction needs table-type
      classification BEFORE persisting. Currently the extractor catches
      tree/lawn/fee schedules as "dimensional standards" (Miami Beach false
      positive: RS-1 "lot=30000" was lawn area). Only Fort Lauderdale has
      reliably-structured dimensional tables in the corpus. Task 9.3b
      (extend ingestion/chunking + table-type detection) blocks multi-muni
      verified coverage. Do NOT persist extracted rows without confirming the
      source chunk is a real dimensional table.

## Architecture decision — 2026-06-26 (user-steered, research-grounded)

Re-prioritized Phase 8 (AgenticRAG + data foundation) AHEAD of Phase 4-7.
Downstream layers (tool registry / HTN planner / ClaimLog / API) must sit on a
correct retriever, not mangled chunks.

**Grounding:** docs/prd/2026-04-30-agentic-research-trace.md + docs/architecture/
agentic-land-use-harness.md.
  * A-RAG (arXiv 2602.03442): hierarchical retrieval > one-shot RAG.
  * SoK Agentic RAG (arXiv 2603.07379): staged retrieval, untrusted content.
  * Architecture §4.3: OrdinanceToolPort as typed boundary; §6: adapter rule
    (same core port, transport only); §9: MCP adapter; §15: store source
    snippets + citations + freshness, not bulk republication.

**Root cause of broken chunks (now fact-based):** the 45,595 existing chunks
were ingested via the Jina/codifier adapter (returns markdown, tables flattened
to prose). <10% of chunks preserve table structure even for Fort Lauderdale.
The native MunicodeScraper (scraper.py, hits api.municode.com, returns raw HTML
per node) + the chunker's _table_to_text (pandas.read_html, preserves tables as
labeled rows) ALREADY EXIST and are correct — but this path was never used to
populate the live DB. No new chunking code needed for the table problem.

**No official Municode MCP exists** (checked MCP registry + npm + GitHub;
closest is wcurrangroome/municoder). "Extract with a Municode MCP" = we build
the OrdinanceToolPort (§4.3) and expose it over MCP (§9). That IS the Municode MCP.

**Plan (3 layers, dependency order):**
  * 8.0  — re-ingest all municode municipalities via native MunicodeScraper
           (fixes table structure for ALL munis; no new chunking code).
  * 8.0b — OrdinanceToolPort (staged retrieval: search_index/open_section/
           follow_cross_ref/read_dimensional_table) + Municode MCP adapter.
  * 8.1-8.4 then build on the correct retriever.

**Deferred:** vision/multimodal retriever (charts/images <10% of verified-fact
data; needs vision model — dedicated story later). Tables are the >90% problem
and are a structured-HTML problem solved by 8.0+8.0b.
