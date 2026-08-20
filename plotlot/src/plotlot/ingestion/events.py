"""Harness events — stable event contracts (Phase 1 — master spec §6).

Every ingestion run + agent analysis run emits structured events with a stable
envelope. Persisted to harness_events, queryable by run, streamable to frontend
(after redaction), deterministic enough for tests. Unknown event types rejected.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any


class IngestionEventType(str, Enum):
    """Master spec §2 ingestion events."""

    SOURCE_AUTHORITY_DISCOVERED = "source_authority_discovered"
    SOURCE_AUTHORITY_VERIFIED = "source_authority_verified"
    SOURCE_AUTHORITY_REJECTED = "source_authority_rejected"
    SOURCE_FETCH_STARTED = "source_fetch_started"
    SOURCE_FETCH_COMPLETED = "source_fetch_completed"
    SOURCE_FETCH_FAILED = "source_fetch_failed"
    RAW_SNAPSHOT_STORED = "raw_snapshot_stored"
    SOURCE_UNCHANGED = "source_unchanged"
    SOURCE_DIFF_DETECTED = "source_diff_detected"
    PARSER_STARTED = "parser_started"
    PARSER_COMPLETED = "parser_completed"
    PARSER_FAILED = "parser_failed"
    SECTION_INDEXED = "section_indexed"
    TABLE_EXTRACTED = "table_extracted"
    CHUNK_CREATED = "chunk_created"
    EMBEDDING_STARTED = "embedding_started"
    EMBEDDING_COMPLETED = "embedding_completed"
    CHUNK_UPSERTED = "chunk_upserted"
    JURISDICTION_QUALITY_SCORED = "jurisdiction_quality_scored"
    FRESHNESS_CHECKED = "freshness_checked"
    GOLD_QUERY_PASSED = "gold_query_passed"
    GOLD_QUERY_FAILED = "gold_query_failed"
    INGESTION_RUN_COMPLETED = "ingestion_run_completed"
    INGESTION_RUN_FAILED = "ingestion_run_failed"


class HarnessEventType(str, Enum):
    """Master spec §3 harness analysis events."""

    RUN_REQUESTED = "run_requested"
    RUN_STARTED = "run_started"
    CONTEXT_BUILT = "context_built"
    SKILL_SELECTED = "skill_selected"
    MODEL_TURN_STARTED = "model_turn_started"
    MODEL_TURN_COMPLETED = "model_turn_completed"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    TOOL_FAILED = "tool_failed"
    EVIDENCE_RECORDED = "evidence_recorded"
    APPROVAL_REQUIRED = "approval_required"
    APPROVAL_DECISION = "approval_decision"
    REPORT_CLAIM_CREATED = "report_claim_created"
    REPORT_CLAIM_REJECTED = "report_claim_rejected"
    REPORT_SECTION_CREATED = "report_section_created"
    REPORT_COMPLETED = "report_completed"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"


_VALID_SEVERITIES = {"debug", "info", "warning", "error"}

# Required payload fields per event type (master spec §2/§3). Events missing
# these are rejected at construction — the testable invariant.
_REQUIRED_PAYLOAD: dict[str, set[str]] = {
    "source_authority_discovered": {"authority_id", "provider", "jurisdiction", "official_status"},
    "source_authority_verified": {"authority_id", "verification_result", "checked_fields"},
    "source_authority_rejected": {"authority_id", "reason"},
    "source_fetch_started": {"authority_id", "source_url"},
    "source_fetch_completed": {
        "authority_id",
        "snapshot_id",
        "http_status",
        "content_hash",
        "bytes",
    },
    "source_fetch_failed": {"authority_id", "source_url", "error", "stage"},
    "raw_snapshot_stored": {"snapshot_id", "content_hash", "raw_storage_url"},
    "source_unchanged": {"authority_id", "snapshot_id", "content_hash"},
    "source_diff_detected": {"authority_id", "old_hash", "new_hash", "changed_sections"},
    "parser_started": {"authority_id", "snapshot_id", "parser_version"},
    "parser_completed": {"authority_id", "sections", "chunks", "tables", "warnings"},
    "parser_failed": {"authority_id", "snapshot_id", "error", "stage"},
    "section_indexed": {"section_id", "section_number_normalized", "chunk_kind"},
    "table_extracted": {"section_id", "table_index", "headers", "row_count"},
    "chunk_created": {"chunk_id", "section_id", "chunk_kind", "chunk_index"},
    "embedding_started": {"authority_id", "chunk_count"},
    "embedding_completed": {"authority_id", "embedded", "failed", "model"},
    "chunk_upserted": {"chunk_id", "operation"},
    "jurisdiction_quality_scored": {"authority_id", "coverage_score", "dimensions"},
    "freshness_checked": {"authority_id", "last_checked_at", "source_version", "stale"},
    "gold_query_passed": {"authority_id", "query_id", "hit"},
    "gold_query_failed": {"authority_id", "query_id", "miss_reason"},
    "ingestion_run_completed": {
        "ingestion_run_id",
        "authority_id",
        "chunks",
        "sections",
        "duration_ms",
    },
    "ingestion_run_failed": {"ingestion_run_id", "authority_id", "error", "stage"},
    "run_requested": {"analysis_run_id", "skill_name", "site_id", "intended_use"},
    "run_started": {"analysis_run_id", "model"},
    "context_built": {"analysis_run_id", "layers", "token_estimate"},
    "skill_selected": {"analysis_run_id", "skill_name"},
    "model_turn_started": {"analysis_run_id", "turn"},
    "model_turn_completed": {"analysis_run_id", "turn", "tool_calls"},
    "tool_started": {"tool_run_id", "tool_name", "risk_class"},
    "tool_completed": {"tool_run_id", "tool_name", "status"},
    "tool_failed": {"tool_run_id", "tool_name", "error"},
    "evidence_recorded": {"evidence_id", "tool_run_id", "claim_key", "source_type"},
    "approval_required": {"approval_id", "tool_run_id", "risk_class", "action_summary"},
    "approval_decision": {"approval_id", "decision", "decided_by"},
    "report_claim_created": {"report_id", "claim_key", "evidence_ids", "material"},
    "report_claim_rejected": {"report_id", "claim_key", "reason"},
    "report_section_created": {"report_id", "section"},
    "report_completed": {"report_id", "analysis_run_id", "claim_count", "uncited_count"},
    "run_completed": {"analysis_run_id", "report_id", "duration_ms"},
    "run_failed": {"analysis_run_id", "error", "stage"},
}

# Redaction: never persist these keys in payload (master spec §4).
_REDACTED_KEYS = {"token", "api_key", "password", "secret", "authorization", "oauth_token"}


def _resolve_type(type_value: IngestionEventType | HarnessEventType | str) -> str:
    """Accept an enum or a string; reject unknown types."""
    if isinstance(type_value, (IngestionEventType, HarnessEventType)):
        return str(type_value.value)
    if isinstance(type_value, str):
        if type_value in {t.value for t in IngestionEventType} or type_value in {
            t.value for t in HarnessEventType
        }:
            return type_value
        raise ValueError(f"Unknown event type: {type_value!r}")
    raise ValueError(f"Event type must be an enum or string, got {type(type_value).__name__}")


@dataclass
class HarnessEvent:
    """Stable event envelope (master spec §6 §1).

    Every ingestion + analysis run emits these. Persisted, queryable, streamable.
    Required payload fields enforced per type. Secrets redacted.
    """

    type: IngestionEventType | HarnessEventType | str
    severity: str
    payload: dict[str, Any]
    id: str = ""
    timestamp: str = ""
    correlation_id: str = ""
    workspace_id: str | None = None
    project_id: str | None = None
    site_id: str | None = None
    analysis_id: str | None = None
    analysis_run_id: str | None = None
    ingestion_run_id: str | None = None
    source_authority_id: str | None = None
    tool_run_id: str | None = None

    def __post_init__(self) -> None:
        # Validate + resolve type (rejects unknown).
        resolved = _resolve_type(self.type)
        object.__setattr__(self, "type", resolved)
        # Validate severity.
        if self.severity not in _VALID_SEVERITIES:
            raise ValueError(
                f"Invalid severity {self.severity!r}; must be one of {sorted(_VALID_SEVERITIES)}"
            )
        # Required payload fields per type (master spec §4 invariant).
        required = _REQUIRED_PAYLOAD.get(resolved, set())
        missing = required - set(self.payload.keys())
        if missing:
            raise ValueError(
                f"Event {resolved!r} missing required payload fields: {sorted(missing)}"
            )
        # Redact secrets from payload (master spec §4).
        redacted = {
            k: ("***REDACTED***" if any(r in k.lower() for r in _REDACTED_KEYS) else v)
            for k, v in self.payload.items()
        }
        object.__setattr__(self, "payload", redacted)
        # Auto-fill id / timestamp / correlation_id.
        if not self.id:
            object.__setattr__(self, "id", f"evt_{uuid.uuid4().hex[:16]}")
        if not self.timestamp:
            object.__setattr__(self, "timestamp", datetime.now(timezone.utc).isoformat())
        if not self.correlation_id:
            object.__setattr__(self, "correlation_id", f"corr_{uuid.uuid4().hex[:12]}")


__all__ = [
    "HarnessEvent",
    "HarnessEventType",
    "IngestionEventType",
]
