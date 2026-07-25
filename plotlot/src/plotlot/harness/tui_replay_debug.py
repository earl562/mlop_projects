from __future__ import annotations

from plotlot.harness.debug_bundle import default_debug_bundle_stores, export_debug_bundle
from plotlot.harness.tui import TuiPanel, TuiRenderRequest, TuiScreen, TuiScreenName


def replay_debug_screen(request: TuiRenderRequest) -> TuiScreen:
    run_id = request.required_run_id()
    bundle = export_debug_bundle(run_id, default_debug_bundle_stores())
    replay = bundle.replay
    return TuiScreen(
        screen=TuiScreenName.REPLAY_DEBUG,
        title="Replay / Debug",
        summary={
            "run_id": str(run_id),
            "status": replay.status,
            "source_mode": replay.source_mode.value,
            "event_count": replay.event_count,
            "evidence_count": len(bundle.evidence),
            "claim_count": len(bundle.claims),
            "calculation_count": len(bundle.calculations),
            "report_count": len(bundle.reports),
            "verification_count": len(bundle.verifications),
            "approval_count": len(bundle.approvals),
            "tool_call_count": len(bundle.tool_calls),
            "redactions": ",".join(bundle.redactions),
        },
        panels=[
            TuiPanel(title="Replay Timeline", items=[item.model_dump(mode="json") for item in replay.timeline]),
            TuiPanel(title="Debug Metadata", items=[bundle.metadata]),
        ],
    )
