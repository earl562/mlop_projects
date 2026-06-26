# Spec — South Florida Ingestion Events

**Status:** Phase 0 specification (event contracts before code).
**Master spec ref:** §6 (Event-Driven Contracts).

## 1. Event envelope (stable, all events)

```json
{
  "id": "evt_...",
  "type": "source_fetch_completed",
  "timestamp": "2026-...",
  "workspace_id": "...",
  "project_id": null,
  "site_id": null,
  "analysis_id": null,
  "analysis_run_id": null,
  "ingestion_run_id": null,
  "source_authority_id": null,
  "tool_run_id": null,
  "correlation_id": "...",
  "severity": "debug | info | warning | error",
  "payload": {}
}
```

Every event persisted to `harness_events` table, queryable by run, streamable
to frontend (after redaction), deterministic enough for tests.

## 2. Ingestion event types + required payload fields

| type | required payload | severity |
|---|---|---|
| `source_authority_discovered` | `authority_id`, `provider`, `jurisdiction`, `official_status` | info |
| `source_authority_verified` | `authority_id`, `verification_result`, `checked_fields` | info |
| `source_authority_rejected` | `authority_id`, `reason` | warning |
| `source_fetch_started` | `authority_id`, `snapshot_id?`, `source_url` | debug |
| `source_fetch_completed` | `authority_id`, `snapshot_id`, `http_status`, `content_hash`, `bytes` | info |
| `source_fetch_failed` | `authority_id`, `source_url`, `error`, `stage` | error |
| `raw_snapshot_stored` | `snapshot_id`, `content_hash`, `raw_storage_url`, `etag?` | info |
| `source_unchanged` | `authority_id`, `snapshot_id`, `content_hash` | info |
| `source_diff_detected` | `authority_id`, `old_hash`, `new_hash`, `changed_sections` | warning |
| `parser_started` | `authority_id`, `snapshot_id`, `parser_version` | debug |
| `parser_completed` | `authority_id`, `sections`, `chunks`, `tables`, `warnings` | info |
| `parser_failed` | `authority_id`, `snapshot_id`, `error`, `stage` | error |
| `section_indexed` | `section_id`, `section_number_normalized`, `chunk_kind` | debug |
| `table_extracted` | `section_id`, `table_index`, `headers`, `row_count` | info |
| `chunk_created` | `chunk_id`, `section_id`, `chunk_kind`, `chunk_index` | debug |
| `embedding_started` | `authority_id`, `chunk_count` | debug |
| `embedding_completed` | `authority_id`, `embedded`, `failed`, `model` | info |
| `chunk_upserted` | `chunk_id`, `operation` (insert\|update) | debug |
| `jurisdiction_quality_scored` | `authority_id`, `coverage_score`, `dimensions` | info |
| `freshness_checked` | `authority_id`, `last_checked_at`, `source_version`, `stale` | info |
| `gold_query_passed` | `authority_id`, `query_id`, `hit` | info |
| `gold_query_failed` | `authority_id`, `query_id`, `miss_reason` | warning |
| `ingestion_run_completed` | `ingestion_run_id`, `authority_id`, `chunks`, `sections`, `duration_ms` | info |
| `ingestion_run_failed` | `ingestion_run_id`, `authority_id`, `error`, `stage` | error |

## 3. Harness analysis event types + required payload fields

| type | required payload | severity |
|---|---|---|
| `run_requested` | `analysis_run_id`, `skill_name`, `site_id`, `intended_use` | info |
| `run_started` | `analysis_run_id`, `model` | info |
| `context_built` | `analysis_run_id`, `layers`, `token_estimate` | debug |
| `skill_selected` | `analysis_run_id`, `skill_name` | info |
| `model_turn_started` | `analysis_run_id`, `turn` | debug |
| `model_turn_completed` | `analysis_run_id`, `turn`, `tool_calls` | debug |
| `tool_started` | `tool_run_id`, `tool_name`, `risk_class` | debug |
| `tool_completed` | `tool_run_id`, `tool_name`, `evidence_ids?`, `status` | info |
| `tool_failed` | `tool_run_id`, `tool_name`, `error` | error |
| `evidence_recorded` | `evidence_id`, `tool_run_id`, `claim_key`, `source_type` | info |
| `approval_required` | `approval_id`, `tool_run_id`, `risk_class`, `action_summary` | warning |
| `approval_decision` | `approval_id`, `decision`, `decided_by` | info |
| `report_claim_created` | `report_id`, `claim_key`, `evidence_ids`, `material` | info |
| `report_claim_rejected` | `report_id`, `claim_key`, `reason` | warning |
| `report_section_created` | `report_id`, `section` | info |
| `report_completed` | `report_id`, `analysis_run_id`, `claim_count`, `uncited_count` | info |
| `run_completed` | `analysis_run_id`, `report_id`, `duration_ms` | info |
| `run_failed` | `analysis_run_id`, `error`, `stage` | error |

## 4. Event invariants (testable)

- Every event has `id`, `type`, `timestamp`, `correlation_id`, `severity`.
- `type` must be in the enumerated set above (unknown type rejected at write).
- Required payload fields present per type (rejected otherwise).
- `severity` ∈ {debug, info, warning, error}.
- Events are append-only (no mutation); `harness_events` table is the audit trail.
- Redaction: secrets/tokens/api-keys/oauth/email-bodies never in payload.

## 5. Definition of Done (Phase 0 — this spec)

- [x] Event envelope defined
- [x] All event types enumerated with required payload fields
- [x] Invariants listed
- [ ] BDD scenarios reference these events
