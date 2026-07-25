from __future__ import annotations

from collections.abc import Sequence

from plotlot.harness.cost_assumption_source import load_cost_assumption_source_catalog
from plotlot.harness.contracts import Report, VerificationResult
from plotlot.harness.municode_source import load_municode_source_catalog
from plotlot.harness.report_inspection import comp_support_snapshot, latest_report
from plotlot.harness.south_florida_gis import load_south_florida_gis_source_catalog
from plotlot.harness.training_ingestion import discover_training_video_sources
from plotlot.harness.tui import TuiPanel, TuiRenderRequest, TuiScreen, TuiScreenName, TuiStores
from plotlot.harness.verification_inspection import verification_payload


def run_monitor_screen(request: TuiRenderRequest, stores: TuiStores) -> TuiScreen:
    run_id = request.required_run_id()
    run = stores.run_store.get_run(run_id)
    events = stores.run_store.get_events(run_id)
    tool_calls = stores.tool_call_ledger.list_tool_calls(run_id=run_id)
    reports = stores.report_ledger.list_reports(run_id=run_id)
    support_snapshot = comp_support_snapshot(latest_report(reports))
    verifications = stores.verification_ledger.list_verifications(run_id=run_id)
    verification = verifications[-1] if verifications else None
    return TuiScreen(
        screen=TuiScreenName.RUN_MONITOR,
        title="Run Monitor",
        summary={
            "run_id": str(run.run_id),
            "status": run.status,
            "source_mode": run.source_mode.value,
            "event_count": len(events),
            "tool_call_count": len(tool_calls),
            "report_id": run.report_id,
            "verification_status": run.verification_status,
            "comp_support_status": support_snapshot.get("status", "unknown"),
            "combined_support_tier": support_snapshot.get("combined_support_tier", "unknown"),
            "land_support_source": support_snapshot.get("land_support_source", "unknown"),
            "jurisdiction_alignment_status": _check_status(verification, "jurisdiction_alignment"),
            "jurisdiction_mismatch_count": _jurisdiction_mismatch_count(verification),
        },
        panels=[
            TuiPanel(
                title="Event Timeline",
                items=[
                    {
                        "sequence": event.sequence,
                        "type": event.type.value,
                        "status": event.status.value if event.status else "",
                        "source": event.source.value,
                    }
                    for event in events
                ],
            ),
            TuiPanel(title="Tool Calls", items=[call.model_dump(mode="json") for call in tool_calls]),
        ],
    )


def evidence_screen(request: TuiRenderRequest, stores: TuiStores) -> TuiScreen:
    run_id = request.required_run_id()
    evidence = stores.evidence_ledger.list_evidence(run_id=run_id)
    return TuiScreen(
        screen=TuiScreenName.EVIDENCE,
        title="Evidence",
        summary={"run_id": str(run_id), "evidence_count": len(evidence)},
        panels=[TuiPanel(title="Evidence Items", items=[item.model_dump(mode="json") for item in evidence])],
    )


def verification_screen(request: TuiRenderRequest, stores: TuiStores) -> TuiScreen:
    run_id = request.required_run_id()
    verifications = stores.verification_ledger.list_verifications(run_id=run_id)
    reports = stores.report_ledger.list_reports(run_id=run_id)
    support_snapshot = comp_support_snapshot(latest_report(reports))
    latest_verification = verifications[-1] if verifications else None
    return TuiScreen(
        screen=TuiScreenName.VERIFICATION,
        title="Verification",
        summary={
            "run_id": str(run_id),
            "verification_count": len(verifications),
            "comp_support_status": support_snapshot.get("status", "unknown"),
            "combined_support_tier": support_snapshot.get("combined_support_tier", "unknown"),
            "jurisdiction_alignment_status": _check_status(latest_verification, "jurisdiction_alignment"),
            "jurisdiction_mismatch_count": _jurisdiction_mismatch_count(latest_verification),
        },
        panels=[
            TuiPanel(
                title="Verification Results",
                items=[
                    verification_payload(item, report=_report_for_verification(reports, item))
                    for item in verifications
                ],
            ),
            TuiPanel(title="Comp Support", items=[support_snapshot] if support_snapshot else []),
        ],
    )


def report_screen(request: TuiRenderRequest, stores: TuiStores) -> TuiScreen:
    run_id = request.required_run_id()
    reports = stores.report_ledger.list_reports(run_id=run_id)
    claims = stores.report_ledger.list_claims(run_id=run_id)
    support_snapshot = comp_support_snapshot(latest_report(reports))
    return TuiScreen(
        screen=TuiScreenName.REPORT,
        title="Report",
        summary={
            "run_id": str(run_id),
            "report_count": len(reports),
            "claim_count": len(claims),
            "comp_support_status": support_snapshot.get("status", "unknown"),
            "combined_support_tier": support_snapshot.get("combined_support_tier", "unknown"),
        },
        panels=[
            TuiPanel(title="Reports", items=[item.model_dump(mode="json") for item in reports]),
            TuiPanel(title="Comp Support", items=[support_snapshot] if support_snapshot else []),
            TuiPanel(title="Claims", items=[item.model_dump(mode="json") for item in claims]),
        ],
    )


def source_catalog_screen(request: TuiRenderRequest) -> TuiScreen:
    gis_sources = load_south_florida_gis_source_catalog(request.source_mode)
    municode_sources = load_municode_source_catalog(request.source_mode)
    cost_sources = load_cost_assumption_source_catalog(request.source_mode)
    return TuiScreen(
        screen=TuiScreenName.SOURCE_CATALOG,
        title="Source Catalog",
        summary={
            "source_mode": request.source_mode.value,
            "gis_source_count": len(gis_sources),
            "municode_source_count": len(municode_sources),
            "cost_source_count": len(cost_sources),
        },
        panels=[
            TuiPanel(title="South Florida GIS", items=[item.model_dump(mode="json") for item in gis_sources]),
            TuiPanel(title="Municode", items=[item.model_dump(mode="json") for item in municode_sources]),
            TuiPanel(title="Cost Assumptions", items=[item.model_dump(mode="json") for item in cost_sources]),
        ],
    )


def training_screen(request: TuiRenderRequest) -> TuiScreen:
    videos = discover_training_video_sources(source_mode=request.source_mode)
    return TuiScreen(
        screen=TuiScreenName.TRAINING,
        title="Training Corpus",
        summary={"source_mode": request.source_mode.value, "video_count": len(videos)},
        panels=[TuiPanel(title="Video Sources", items=[item.model_dump(mode="json") for item in videos])],
    )


def _check_status(verification: VerificationResult | None, key: str) -> str:
    if verification is None:
        return "unknown"
    value = verification.checks.get(key)
    return str(value or "unknown")


def _jurisdiction_mismatch_count(verification: VerificationResult | None) -> int:
    if verification is None:
        return 0
    return len(verification.jurisdiction_mismatches)


def _report_for_verification(
    reports: Sequence[Report],
    verification: VerificationResult,
) -> Report | None:
    for report in reports:
        if report.report_id == verification.report_id:
            return report
    return None
