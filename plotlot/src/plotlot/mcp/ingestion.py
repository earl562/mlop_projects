from __future__ import annotations

from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass

from fastmcp.server.dependencies import get_context

from plotlot.ingestion.acp_coordinator import run_on_demand_ingestion
from plotlot.ingestion.acp_models import IngestProgress, IngestRequest
from plotlot.mcp.tool_types import JsonObject, JsonValue

type IngestionRunner = Callable[[IngestRequest], AsyncGenerator[IngestProgress, None]]


@dataclass(frozen=True, slots=True)
class McpIngestInput:
    municipality: str
    state: str
    county: str | None = None


@dataclass(frozen=True, slots=True)
class _McpEvidenceContext:
    workspace_id: str | None = None
    project_id: str | None = None
    site_id: str | None = None
    analysis_id: str | None = None
    analysis_run_id: str | None = None
    tool_run_id: str | None = None


def _clean_text(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _metadata_context() -> _McpEvidenceContext:
    try:
        context = get_context()
    except RuntimeError:
        return _McpEvidenceContext()

    request_context = context.request_context
    if request_context is None or request_context.meta is None:
        return _McpEvidenceContext()

    meta = request_context.meta
    return _McpEvidenceContext(
        workspace_id=_clean_text(getattr(meta, "workspace_id", None)),
        project_id=_clean_text(getattr(meta, "project_id", None)),
        site_id=_clean_text(getattr(meta, "site_id", None)),
        analysis_id=_clean_text(getattr(meta, "analysis_id", None)),
        analysis_run_id=_clean_text(getattr(meta, "analysis_run_id", None)),
        tool_run_id=_clean_text(getattr(meta, "tool_run_id", None)),
    )


def _ingest_request(input_data: McpIngestInput) -> IngestRequest:
    context = _metadata_context()
    return IngestRequest(
        municipality=input_data.municipality,
        state=input_data.state,
        county=input_data.county,
        trigger="mcp",
        workspace_id=context.workspace_id,
        project_id=context.project_id,
        site_id=context.site_id,
        analysis_id=context.analysis_id,
        analysis_run_id=context.analysis_run_id,
        tool_run_id=context.tool_run_id,
    )


def _progress_payload(progress: IngestProgress) -> JsonObject:
    return {
        "stage": progress.stage,
        "message": progress.message,
        "chunks_done": progress.chunks_done,
        "chunks_total": progress.chunks_total,
        "complete": progress.complete,
        "error": progress.error,
        "evidence_ids": list(progress.evidence_ids),
        "quality_flags": list(progress.quality_flags),
        "source_record_count": progress.source_record_count,
    }


def _int_value(value: JsonValue, default: int = 0) -> int:
    return value if isinstance(value, int) else default


def _text_value(value: JsonValue) -> str | None:
    return value if isinstance(value, str) else None


def _evidence_ids(value: JsonValue | None) -> list[JsonValue]:
    if not isinstance(value, list):
        return []
    return [evidence_id for evidence_id in value if isinstance(evidence_id, str)]


def _quality_flags(value: JsonValue | None) -> list[JsonValue]:
    if not isinstance(value, list):
        return []
    return [quality_flag for quality_flag in value if isinstance(quality_flag, str)]


async def run_ingest_municipality(
    input_data: McpIngestInput,
    runner: IngestionRunner = run_on_demand_ingestion,
) -> JsonObject:
    request = _ingest_request(input_data)
    events: list[JsonValue] = []

    async for progress in runner(request):
        events.append(_progress_payload(progress))

    final: JsonObject = events[-1] if events and isinstance(events[-1], dict) else {}
    success = final.get("stage") == "complete"
    chunks_stored = _int_value(final.get("chunks_done"), default=0) if success else 0
    source_record_count = _int_value(final.get("source_record_count"), default=0)

    return {
        "municipality": input_data.municipality,
        "state": input_data.state.upper(),
        "county": input_data.county,
        "success": success,
        "chunks_stored": chunks_stored,
        "evidence_ids": _evidence_ids(final.get("evidence_ids")),
        "quality_flags": _quality_flags(final.get("quality_flags")),
        "source_record_count": source_record_count,
        "error": None if success else _text_value(final.get("error")),
        "progress": events,
    }
