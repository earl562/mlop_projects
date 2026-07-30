from __future__ import annotations

import pytest

from plotlot.harness.approval_store import (
    ApprovalAlreadyResolvedError,
    LocalApprovalLedger,
)
from plotlot.harness.contracts import (
    ApprovalStatus,
    PlotLotEventSource,
    PlotLotEventType,
    RiskLevel,
    RunId,
)


def test_local_approval_ledger_records_request_and_decision_events(tmp_path) -> None:
    ledger = LocalApprovalLedger(tmp_path / "approvals.json")

    # Given a local fixture run needs an explicit approval.
    approval = ledger.request_approval(
        run_id=RunId("run_fixture_approval_store"),
        requested_action="export_lender_package",
        risk_level=RiskLevel.HIGH,
        reason="Exporting a lender package requires analyst approval.",
        source=PlotLotEventSource.CLI,
        policy_ids=["fixture-export-approval"],
    )

    assert approval.status == ApprovalStatus.PENDING
    assert approval.approval_id.startswith("apr_run_fixture_approval_store_export_lender_package")
    assert ledger.list_approvals(run_id=RunId("run_fixture_approval_store")) == [approval]
    assert [event.type for event in ledger.list_events(RunId("run_fixture_approval_store"))] == [
        PlotLotEventType.APPROVAL_REQUESTED
    ]

    # When an analyst approves it, the ledger stores the decision and emits a typed event.
    resolved = ledger.resolve_approval(
        approval.approval_id,
        decision=ApprovalStatus.APPROVED,
        resolved_by="analyst@example.test",
    )

    assert resolved.status == ApprovalStatus.APPROVED
    assert resolved.resolved_by == "analyst@example.test"
    assert [event.type for event in ledger.list_events(RunId("run_fixture_approval_store"))] == [
        PlotLotEventType.APPROVAL_REQUESTED,
        PlotLotEventType.APPROVAL_GRANTED,
    ]

    # Then a decided approval cannot be changed silently.
    with pytest.raises(ApprovalAlreadyResolvedError):
        ledger.resolve_approval(
            approval.approval_id,
            decision=ApprovalStatus.DENIED,
            resolved_by="second-reviewer@example.test",
        )
