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
