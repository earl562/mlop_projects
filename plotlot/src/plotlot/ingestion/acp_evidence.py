from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from plotlot.ingestion.acp_models import IngestRequest
from plotlot.ingestion.adapters.result import IngestionAdapterResult, IngestionSourceRecord
from plotlot.pipeline.lookup_snapshot_json import JsonValue
from plotlot.storage.models import EvidenceItem

_INGESTION_TOOL_NAME = "ingest_municipality"


@dataclass(frozen=True, slots=True)
class IngestionEvidenceContext:
    workspace_id: str
    project_id: str
    site_id: str | None = None
    analysis_id: str | None = None
    analysis_run_id: str | None = None
    tool_run_id: str | None = None


def ingestion_evidence_context_from_request(
    request: IngestRequest,
) -> IngestionEvidenceContext | None:
    if request.workspace_id is None or request.project_id is None:
        return None
    return IngestionEvidenceContext(
        workspace_id=request.workspace_id,
        project_id=request.project_id,
        site_id=request.site_id,
        analysis_id=request.analysis_id,
        analysis_run_id=request.analysis_run_id,
        tool_run_id=request.tool_run_id,
    )


async def persist_ingestion_source_records(
    session: AsyncSession,
    context: IngestionEvidenceContext,
    result: IngestionAdapterResult,
) -> tuple[str, ...]:
    evidence_ids: list[str] = []
    for record in result.source_records:
        evidence_id = _evidence_id(context, record)
        row = await session.get(EvidenceItem, evidence_id)
        if row is None:
            session.add(_new_evidence_row(evidence_id, context, record))
        else:
            _update_evidence_row(row, context, record)
        evidence_ids.append(evidence_id)
    if evidence_ids:
        await session.flush()
    return tuple(evidence_ids)


def _new_evidence_row(
    evidence_id: str,
    context: IngestionEvidenceContext,
    record: IngestionSourceRecord,
) -> EvidenceItem:
    return EvidenceItem(
        id=evidence_id,
        workspace_id=context.workspace_id,
        project_id=context.project_id,
        site_id=context.site_id,
        analysis_id=context.analysis_id,
        analysis_run_id=context.analysis_run_id,
        tool_run_id=context.tool_run_id,
        claim_key=_claim_key(record),
        value_json=_value_json(record),
        source_type=record.source_type,
        source_url=record.source_url or None,
        source_title=record.source_title,
        source_excerpt=None,
        retrieval_method="ingestion_adapter",
        trust_label=_trust_label(record),
        source_version=record.schema_version,
        content_hash=_content_hash(record),
        tool_name=_INGESTION_TOOL_NAME,
        confidence=_confidence_label(record.confidence),
        metadata_json=_metadata_json(record),
        retrieved_at=_retrieved_at(record.retrieved_at),
    )


def _update_evidence_row(
    row: EvidenceItem,
    context: IngestionEvidenceContext,
    record: IngestionSourceRecord,
) -> None:
    setattr(row, "workspace_id", context.workspace_id)
    setattr(row, "project_id", context.project_id)
    setattr(row, "site_id", context.site_id)
    setattr(row, "analysis_id", context.analysis_id)
    setattr(row, "analysis_run_id", context.analysis_run_id)
    setattr(row, "tool_run_id", context.tool_run_id)
    setattr(row, "value_json", _value_json(record))
    setattr(row, "source_url", record.source_url or None)
    setattr(row, "source_title", record.source_title)
    setattr(row, "source_version", record.schema_version)
    setattr(row, "content_hash", _content_hash(record))
    setattr(row, "confidence", _confidence_label(record.confidence))
    setattr(row, "metadata_json", _metadata_json(record))
    setattr(row, "retrieved_at", _retrieved_at(record.retrieved_at))


def _evidence_id(context: IngestionEvidenceContext, record: IngestionSourceRecord) -> str:
    raw_key = "|".join(
        (
            context.workspace_id,
            context.project_id,
            record.source_url,
            record.raw_artifact_ref,
            record.parser_version,
            record.schema_version,
        )
    )
    return f"ev_ing_{hashlib.sha256(raw_key.encode()).hexdigest()[:28]}"


def _value_json(record: IngestionSourceRecord) -> dict[str, JsonValue]:
    return {
        "source_url": record.source_url,
        "source_title": record.source_title,
        "quality_score": record.quality_score,
        "quality_flags": [str(flag) for flag in record.quality_flags],
        "warnings": [str(warning) for warning in record.warnings],
    }


def _metadata_json(record: IngestionSourceRecord) -> dict[str, JsonValue]:
    return {
        "source_authority": record.source_authority,
        "publisher": record.publisher,
        "effective_date": record.effective_date,
        "parser_version": record.parser_version,
        "schema_version": record.schema_version,
        "query_parameters": [
            {"name": name, "value": value} for name, value in record.query_parameters
        ],
        "raw_artifact_ref": record.raw_artifact_ref,
        "lineage": [str(item) for item in record.lineage],
        "quality_score": record.quality_score,
        "quality_flags": [str(flag) for flag in record.quality_flags],
        "warnings": [str(warning) for warning in record.warnings],
    }


def _claim_key(record: IngestionSourceRecord) -> str:
    return f"ingestion_source:{record.source_title or record.source_url}"


def _trust_label(record: IngestionSourceRecord) -> str:
    if record.source_type.startswith("official") or "official" in record.source_authority:
        return "high"
    return "medium"


def _confidence_label(confidence: float) -> str:
    if confidence >= 0.8:
        return "high"
    if confidence >= 0.5:
        return "medium"
    return "low"


def _content_hash(record: IngestionSourceRecord) -> str:
    value = "|".join((record.source_url, record.raw_artifact_ref, record.parser_version))
    return hashlib.sha256(value.encode()).hexdigest()


def _retrieved_at(value: str) -> datetime:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return datetime.now(UTC)
