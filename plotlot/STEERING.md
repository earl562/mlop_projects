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
