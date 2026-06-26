# Spec — South Florida Ordinance Ingestion

**Status:** Phase 0 specification (no production code yet — this file locks the contract).
**Master spec ref:** §5 (South Florida Ordinance Ingestion Spec), §7 (Database Plan), §8 (Module Plan).
**Related:** `docs/architecture/agentic-land-use-harness.md` §4.3 (Ordinance Service), §15 (Municode/OpenData).

## 1. Goal

A provider-agnostic, source-authority-driven ingestion system that ingests
zoning / land-development ordinances for every South Florida jurisdiction
(Miami-Dade, Broward, Palm Beach counties + incorporated municipalities +
unincorporated county jurisdictions), stores raw snapshots before parsing,
and produces evidence-searchable chunks with provenance + freshness + legal
caveats — never hallucinated.

## 2. Domain model

The ingestion unit is **not** "a city." It is a `JurisdictionSourceAuthority`:

```
JurisdictionSourceAuthority
    -> OrdinanceSourceSnapshot   (raw fetch, content-hashed)
        -> OrdinanceSection     (parsed, normalized)
            -> OrdinanceChunk   (embedded, evidence-searchable)
                -> EvidenceItem (claim-backed)
```

### JurisdictionSourceAuthority
- `id`, `state`, `county`, `municipality`
- `jurisdiction_type`: county | municipality | special_district
- `authority_scope`: zoning | land_development | code_of_ordinances | gis_zoning | overlays | comp_plan | adopted_ordinances
- `provider`: official_html | official_pdf | municode | ecode360 | amlegal | codepublishing | municipal_codes | encodeplus | arcgis | manual
- `canonical_url`, `source_url`, `source_title`
- `official_status`: official | publisher_copy | informational | unknown
- `legal_caveat` (always present for ordinance sources)
- `freshness_policy`: live_check | daily | weekly | monthly | manual
- `last_checked_at`, `last_ingested_at`, `source_version`, `supplement_number`, `effective_date`
- `ingestion_status`, `coverage_score`, `metadata_json`

### OrdinanceSourceSnapshot
- `id`, `source_authority_id`, `source_url`, `final_url`, `fetched_at`
- `http_status`, `content_type`, `content_hash` (deterministic)
- `raw_storage_url`, `raw_text_excerpt`, `etag`, `last_modified`
- `source_version`, `metadata_json`
- **Natural key:** `(source_authority_id, content_hash)` — unchanged source reuses snapshot.

### OrdinanceSection (extends existing `ordinance_sections` table)
Add: `source_authority_id`, `snapshot_id`, `source_version`, `effective_date`,
`supplement_number`, `section_number_normalized`, `content_hash`, `parser_version`, `quality_flags`.
**Natural key:** `(source_authority_id, section_number_normalized, content_hash)`.

### OrdinanceChunk (extends existing `ordinance_chunks` table)
Add: `source_authority_id`, `snapshot_id`, `ordinance_section_id`,
`chunk_kind` (narrative | dimensional_table | use_table | parking | definition | overlay | procedure | unknown),
`parser_version`, `quality_flags`, `table_row_key`, `source_page`, `source_anchor`.
**Natural key:** `(ordinance_section_id, chunk_index, content_hash)`.

## 3. Provider priority

1. Official API / official machine-readable source
2. Official HTML
3. Official PDF
4. Municode / CivicPlus
5. eCode360 / General Code
6. American Legal
7. Code Publishing
8. municipal.codes
9. enCodePlus
10. manual upload
11. discovery-only web fallback (cannot support a zoning conclusion until verified + promoted)

## 4. South Florida special handling

- **Miami-Dade County unincorporated zoning** = separate authority from incorporated cities.
- **Broward County** land development / zoning sources = separate from municipalities.
- **Palm Beach County ULDC** = base code PDFs + adopted ordinances not yet codified (indexed separately, freshness caveats).
- **City of Miami / Miami 21** = special authority; must include current-source caveats; historical/educational text is not sole definitive authority.
- **Parcel zoning GIS sources** linked separately from ordinance text (OpenData/ArcGIS = `gis_zoning` scope).

## 5. Rate-limit reality (from prior work)

- `library.municode.com/api/*` is one rate-limit bucket (~1 successful fetch/hour, unkeyed).
  Cached discovery (`~/.plotlot/discovery_cache.json`) holds 416 FL ClientIDs from the one successful fetch.
- `api.municode.com` (content host) is **unthrottled** but needs `jobId`+`productId` from the library API.
- **Implication:** ingestion must be paced + cached + idempotent. Re-ingestion of unchanged source emits `source_unchanged` (no duplicate work). A Municode API key / licensed access (arch doc §15) removes the throttle.

## 6. Idempotency invariants

- Unchanged source (same `content_hash`) → reuse snapshot, emit `source_unchanged`, no duplicate sections/chunks.
- Changed source → `source_diff_detected`, re-parse changed sections, update affected chunks, recompute quality score.
- Re-ingestion never duplicates rows (natural-key upserts).

## 7. Legal/product safety (every ordinance citation)

Every `EvidenceItem` derived from an ordinance source must carry:
- `retrieved_at` (timestamp)
- `source_url`
- `publisher` / `source`
- `jurisdiction`
- `legal_caveat`: "Online code may not be the official/current copy; verify with municipality before action."

## 8. Definition of Done (Phase 0 — this spec)

- [x] This spec committed
- [ ] Event contracts defined (`south_florida_ingestion_events.md`)
- [ ] BDD scenarios written (`bdd/south_florida_zoning_harness.feature`)
- [ ] No production code yet (test scaffolds only)
