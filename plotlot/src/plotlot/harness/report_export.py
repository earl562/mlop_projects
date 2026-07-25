from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Final, assert_never

from pydantic import Field, field_validator

from plotlot.harness.contracts import (
    JsonObject,
    PlotLotEvent,
    PlotLotEventSource,
    PlotLotEventStatus,
    PlotLotEventType,
    Report,
    ReportId,
    ReportStatus,
    RunId,
    SourceMode,
)
from plotlot.harness.contracts.base import HarnessContract, utc_now
from plotlot.harness.report_store import LocalReportLedger, default_report_ledger
from plotlot.harness.run_store import (
    HarnessRunNotFoundError,
    LocalHarnessRunStore,
    default_harness_run_store,
)

REPORT_EXPORT_DIR_ENV: Final = "PLOTLOT_HARNESS_REPORT_EXPORT_DIR"


class ReportExportFormat(StrEnum):
    MARKDOWN = "markdown"


class ReportArtifactExportRequest(HarnessContract):
    report_id: ReportId
    export_format: ReportExportFormat = ReportExportFormat.MARKDOWN
    export_dir: Path | None = None


class ReportArtifactExport(HarnessContract):
    report_id: ReportId
    run_id: RunId
    artifact_uri: str = Field(min_length=1)
    file_path: str = Field(min_length=1)
    export_format: ReportExportFormat
    content_type: str = Field(min_length=1)
    exported_at: datetime = Field(default_factory=utc_now)

    @field_validator("exported_at")
    @classmethod
    def _exported_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("exported_at must be timezone-aware")
        return value


@dataclass(frozen=True, slots=True)
class ReportExportStores:
    report_ledger: LocalReportLedger
    run_store: LocalHarnessRunStore


def export_report_artifact(
    request: ReportArtifactExportRequest,
    *,
    report_ledger: LocalReportLedger | None = None,
    run_store: LocalHarnessRunStore | None = None,
) -> ReportArtifactExport:
    stores = ReportExportStores(
        report_ledger=report_ledger or default_report_ledger(),
        run_store=run_store or default_harness_run_store(),
    )
    report = stores.report_ledger.get_report(request.report_id)
    export_path = _report_export_path(report, request)
    export_path.parent.mkdir(parents=True, exist_ok=True)
    export_path.write_text(_export_content(report, request.export_format), encoding="utf-8")
    export = ReportArtifactExport(
        report_id=report.report_id,
        run_id=report.run_id,
        artifact_uri=export_path.resolve().as_uri(),
        file_path=str(export_path),
        export_format=request.export_format,
        content_type=_content_type(request.export_format),
    )
    stores.report_ledger.save_report(_report_with_export_uri(report, export.artifact_uri))
    _append_export_event(stores.run_store, report, export)
    return export


def default_report_export_dir() -> Path:
    configured = os.environ.get(REPORT_EXPORT_DIR_ENV)
    if configured:
        return Path(configured).expanduser()
    state_home = os.environ.get("XDG_STATE_HOME")
    base = Path(state_home).expanduser() if state_home else Path.home() / ".local" / "state"
    return base / "plotlot" / "report-exports"


def _report_export_path(report: Report, request: ReportArtifactExportRequest) -> Path:
    root = request.export_dir or default_report_export_dir()
    match request.export_format:
        case ReportExportFormat.MARKDOWN:
            return root / f"{_safe_filename(str(report.report_id))}.md"
        case unreachable:
            assert_never(unreachable)


def _export_content(report: Report, export_format: ReportExportFormat) -> str:
    match export_format:
        case ReportExportFormat.MARKDOWN:
            return _markdown_report(report)
        case unreachable:
            assert_never(unreachable)


def _content_type(export_format: ReportExportFormat) -> str:
    match export_format:
        case ReportExportFormat.MARKDOWN:
            return "text/markdown"
        case unreachable:
            assert_never(unreachable)


def _markdown_report(report: Report) -> str:
    sections = "\n\n".join(_markdown_section(section) for section in report.sections)
    preliminary = report.status is not ReportStatus.FINAL or report.source_mode is not SourceMode.LIVE
    guidance_lines = _guidance_summary_lines(report.sections)
    return "\n".join(
        [
            f"# {report.title}",
            "",
            f"- Report ID: {report.report_id}",
            f"- Run ID: {report.run_id}",
            f"- Status: {report.status.value}",
            f"- Source mode: {report.source_mode.value}",
            f"- Preliminary: {str(preliminary).lower()}",
            *guidance_lines,
            "",
            "## Sections",
            sections or "No sections generated.",
            "",
            "## Traceability",
            f"- Claim IDs: {', '.join(str(claim_id) for claim_id in report.claims) or 'none'}",
            f"- Evidence IDs: {', '.join(str(evidence_id) for evidence_id in report.evidence_ids) or 'none'}",
            f"- Calculation IDs: {', '.join(report.calculation_ids) or 'none'}",
        ]
    )


def _markdown_section(section: JsonObject) -> str:
    title = section.get("title", "Untitled Section")
    return f"### {title}\n\n```json\n{json.dumps(section, indent=2, sort_keys=True)}\n```"


def _guidance_summary_lines(sections: list[JsonObject]) -> list[str]:
    for section in sections:
        acquisition_guidance = section.get("acquisition_guidance")
        if not isinstance(acquisition_guidance, dict):
            continue
        lines = ["", "## Acquisition Guidance"]
        lines.extend(
            [
                f"- Market signal verification: {_prettify_label(acquisition_guidance.get('market_signal_verification_status'))}",
                f"- Recommendation confidence: {_prettify_label(acquisition_guidance.get('recommendation_confidence'))}",
                f"- Recommended action: {_prettify_label(acquisition_guidance.get('recommended_action'))}",
                f"- Guidance basis: {_prettify_label(acquisition_guidance.get('basis'))}",
                f"- Market validation required: {_yes_no(acquisition_guidance.get('requires_market_signal_validation'))}",
            ]
        )
        comp_support_summary = section.get("comp_support_summary")
        if isinstance(comp_support_summary, dict):
            lines.extend(
                [
                    f"- Comp support check: {_prettify_label(comp_support_summary.get('status'))}",
                    f"- Comp support reason: {_prettify_label(comp_support_summary.get('reason'))}",
                    f"- Comp support tier: {_prettify_label(comp_support_summary.get('combined_support_tier'))}",
                    f"- Land support source: {_prettify_label(comp_support_summary.get('land_support_source'))}",
                    f"- Land support fit score: {_format_score(comp_support_summary.get('land_support_fit_score'))}",
                    f"- Exit support fit score: {_format_score(comp_support_summary.get('exit_support_fit_score'))}",
                    f"- Comping underwriting status: {_prettify_label(comp_support_summary.get('comping_underwriting_status'))}",
                ]
            )
            blocker = comp_support_summary.get("comping_underwriting_blocker")
            if isinstance(blocker, str) and blocker.strip():
                lines.append(f"- Comping underwriting blocker: {_prettify_label(blocker)}")
        reconciliation = section.get("contextual_land_listing_reconciliation")
        if isinstance(reconciliation, dict) and reconciliation:
            lines.extend(
                [
                    f"- County reconciliation status: {_prettify_label(reconciliation.get('status'))}",
                    f"- County reconciliation attempted candidates: {_format_count(reconciliation.get('attempted_candidate_count'))}",
                    f"- County reconciliation matched candidates: {_format_count(reconciliation.get('reconciled_candidate_count'))}",
                    f"- County reconciliation rejected candidates: {_format_count(reconciliation.get('rejected_candidate_count'))}",
                ]
            )
        decision_trace = section.get("comping_decision_trace")
        if isinstance(decision_trace, dict) and decision_trace:
            lines.extend(
                [
                    f"- Comping search phase: {_prettify_label(decision_trace.get('search_phase_reached'))}",
                    f"- Comping accepted land comps: {_format_count(decision_trace.get('accepted_land_comp_count'))}",
                    f"- Comping contextual listing comps: {_format_count(decision_trace.get('contextual_public_listing_count'))}",
                    f"- Comping next action: {_prettify_label(decision_trace.get('next_required_action'))}",
                ]
            )
        return lines
    return []


def _prettify_label(value: object) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip().replace("_", " ")
    return "unknown"


def _format_score(value: object) -> str:
    if isinstance(value, int | float):
        return f"{float(value):.3f}"
    return "unknown"


def _format_count(value: object) -> str:
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return "unknown"


def _yes_no(value: object) -> str:
    if isinstance(value, bool):
        return "yes" if value else "no"
    return "unknown"


def _safe_filename(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in {"-", "_"} else "_" for char in value)
    return safe or "report"


def _report_with_export_uri(report: Report, artifact_uri: str) -> Report:
    export_urls = list(report.export_urls)
    if artifact_uri not in export_urls:
        export_urls.append(artifact_uri)
    return report.model_copy(update={"export_urls": export_urls})


def _append_export_event(
    run_store: LocalHarnessRunStore,
    report: Report,
    export: ReportArtifactExport,
) -> None:
    event = PlotLotEvent(
        run_id=report.run_id,
        sequence=1,
        type=PlotLotEventType.REPORT_EXPORTED,
        source=PlotLotEventSource.REPORT,
        status=PlotLotEventStatus.COMPLETED,
        source_mode=report.source_mode,
        payload={
            "report_id": str(report.report_id),
            "artifact_uri": export.artifact_uri,
            "file_path": export.file_path,
            "format": export.export_format.value,
        },
    )
    try:
        run_store.append_events(report.run_id, [event])
    except HarnessRunNotFoundError:
        return
