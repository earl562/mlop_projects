from __future__ import annotations

from collections.abc import AsyncGenerator, Callable, Mapping
from dataclasses import dataclass

from plotlot.ingestion.acp_coordinator import run_on_demand_ingestion
from plotlot.ingestion.acp_models import IngestProgress, IngestRequest
from plotlot.land_use.models import ToolContext
from plotlot.pipeline.lookup_snapshot_json import JsonValue

type IngestionRunner = Callable[[IngestRequest], AsyncGenerator[IngestProgress, None]]


@dataclass(frozen=True, slots=True)
class IngestMunicipalityInput:
    municipality: str
    state: str
    county: str | None


def _text_arg(args: Mapping[str, JsonValue], key: str) -> str:
    value = args.get(key)
    return value.strip() if isinstance(value, str) else ""


def _optional_text_arg(args: Mapping[str, JsonValue], key: str) -> str | None:
    value = _text_arg(args, key)
    return value or None


def _input_from_args(args: Mapping[str, JsonValue]) -> IngestMunicipalityInput | None:
    municipality = _text_arg(args, "municipality")
    state = _text_arg(args, "state").upper()
    if not municipality or not state:
        return None
    return IngestMunicipalityInput(
        municipality=municipality,
        state=state,
        county=_optional_text_arg(args, "county"),
    )


def _request_from_context(
    input_data: IngestMunicipalityInput,
    context: ToolContext,
) -> IngestRequest:
    return IngestRequest(
        municipality=input_data.municipality,
        state=input_data.state,
        county=input_data.county,
        trigger="tool_call",
        workspace_id=context.workspace_id,
        project_id=context.project_id,
        site_id=context.site_id,
        analysis_id=context.analysis_id,
        analysis_run_id=context.analysis_run_id,
        tool_run_id=context.tool_run_id,
    )


def _progress_payload(progress: IngestProgress) -> dict[str, JsonValue]:
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


def _final_progress(events: list[JsonValue]) -> dict[str, JsonValue]:
    final = events[-1] if events else {}
    return final if isinstance(final, dict) else {}


def _evidence_ids(final: Mapping[str, JsonValue]) -> list[JsonValue]:
    raw_ids = final.get("evidence_ids")
    if not isinstance(raw_ids, list):
        return []
    return [evidence_id for evidence_id in raw_ids if isinstance(evidence_id, str)]


def _quality_flags(final: Mapping[str, JsonValue]) -> list[JsonValue]:
    raw_flags = final.get("quality_flags")
    if not isinstance(raw_flags, list):
        return []
    return [quality_flag for quality_flag in raw_flags if isinstance(quality_flag, str)]


async def handle_ingest_municipality(
    args: Mapping[str, JsonValue],
    context: ToolContext,
    runner: IngestionRunner | None = None,
) -> dict[str, JsonValue]:
    input_data = _input_from_args(args)
    if input_data is None:
        return {
            "status": "error",
            "municipality": "",
            "state": "",
            "county": None,
            "chunks_stored": 0,
            "evidence_ids": [],
            "quality_flags": [],
            "source_record_count": 0,
            "progress": [],
            "message": "municipality and state are required",
        }

    request = _request_from_context(input_data, context)
    ingestion_runner = runner or run_on_demand_ingestion
    events: list[JsonValue] = []
    async for progress in ingestion_runner(request):
        events.append(_progress_payload(progress))

    final = _final_progress(events)
    success = final.get("stage") == "complete"
    chunks_done = final.get("chunks_done")
    chunks_stored = chunks_done if success and isinstance(chunks_done, int) else 0
    error = final.get("error")
    evidence_ids = _evidence_ids(final)
    quality_flags = _quality_flags(final)
    source_record_count = final.get("source_record_count")

    return {
        "status": "success" if success else "error",
        "municipality": input_data.municipality,
        "state": input_data.state,
        "county": input_data.county,
        "chunks_stored": chunks_stored,
        "evidence_ids": evidence_ids,
        "quality_flags": quality_flags,
        "source_record_count": source_record_count if isinstance(source_record_count, int) else 0,
        "progress": events,
        "message": str(final.get("message") or ""),
        "error": error if isinstance(error, str) else None,
    }
