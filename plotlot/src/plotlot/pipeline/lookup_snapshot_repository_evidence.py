from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.pipeline.lookup_snapshot_json import JsonValue
from plotlot.pipeline.lookup_snapshot_store import LookupSnapshotEvidenceRecord
from plotlot.pipeline.lookup_snapshot_repository_types import (
    LOOKUP_TOOL_NAME,
    LookupSnapshotPersistenceContext,
)
from plotlot.storage.models import EvidenceItem


async def upsert_evidence_item(
    session: AsyncSession,
    snapshot_id: str,
    tool_run_id: str,
    context: LookupSnapshotPersistenceContext,
    project_id: str,
    site_id: str,
    record: LookupSnapshotEvidenceRecord,
) -> None:
    evidence_id = str(record.evidence_id)
    retrieved_at = _retrieved_at(record)
    metadata_json = _evidence_metadata(snapshot_id, record)
    value_json = _evidence_value(record)
    row = await session.get(EvidenceItem, evidence_id)
    if row is None:
        session.add(
            EvidenceItem(
                id=evidence_id,
                workspace_id=context.workspace_id,
                project_id=project_id,
                site_id=site_id,
                analysis_id=None,
                analysis_run_id=snapshot_id,
                tool_run_id=tool_run_id,
                claim_key=_claim_key(record),
                value_json=value_json,
                source_type=record.source_type,
                source_url=record.source_url or None,
                source_title=record.source_title,
                source_excerpt=None,
                retrieval_method="lookup_snapshot_ingestion",
                trust_label=_trust_label(record.source_authority),
                source_version=record.schema_version,
                content_hash=_content_hash(evidence_id),
                tool_name=LOOKUP_TOOL_NAME,
                confidence=_confidence_label(record.confidence),
                metadata_json=metadata_json,
                retrieved_at=retrieved_at,
            )
        )
    else:
        setattr(row, "analysis_run_id", snapshot_id)
        setattr(row, "tool_run_id", tool_run_id)
        setattr(row, "value_json", value_json)
        setattr(row, "metadata_json", metadata_json)
        setattr(row, "retrieved_at", retrieved_at)
    await session.flush()


def _evidence_metadata(
    snapshot_id: str,
    record: LookupSnapshotEvidenceRecord,
) -> dict[str, JsonValue]:
    return {
        "lookup_snapshot_id": snapshot_id,
        "source_authority": record.source_authority,
        "publisher": record.publisher,
        "source_url": record.source_url,
        "source_title": record.source_title,
        "effective_date": record.effective_date,
        "parser_version": record.parser_version,
        "schema_version": record.schema_version,
        "raw_artifact_ref": record.raw_artifact_ref,
        "query_parameters": [str(item) for item in record.query_parameters],
        "lineage": [str(item) for item in record.lineage],
        "calculation_outputs": [str(item) for item in record.calculation_outputs],
        "quality_score": record.quality_score,
        "quality_flags": [str(item) for item in record.quality_flags],
        "warnings": [str(item) for item in record.warnings],
    }


def _evidence_value(record: LookupSnapshotEvidenceRecord) -> dict[str, JsonValue]:
    return {
        "evidence_id": str(record.evidence_id),
        "normalized_fields": [str(field) for field in record.normalized_fields],
        "calculation_outputs": [str(item) for item in record.calculation_outputs],
        "confidence": record.confidence,
        "quality_score": record.quality_score,
        "quality_flags": [str(item) for item in record.quality_flags],
    }


def _claim_key(record: LookupSnapshotEvidenceRecord) -> str:
    if record.normalized_fields:
        return str(record.normalized_fields[0])
    return str(record.evidence_id)


def _trust_label(source_authority: str) -> str:
    if source_authority.startswith("official_"):
        return "high"
    return "medium"


def _confidence_label(confidence: float) -> str:
    if confidence >= 0.8:
        return "high"
    if confidence >= 0.5:
        return "medium"
    return "low"


def _content_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _retrieved_at(record: LookupSnapshotEvidenceRecord) -> datetime:
    try:
        return datetime.fromisoformat(record.retrieved_at)
    except ValueError:
        return datetime.now(UTC)
