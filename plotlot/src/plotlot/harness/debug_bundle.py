from __future__ import annotations

from dataclasses import dataclass

from pydantic import Field

from plotlot.harness.approval_store import LocalApprovalLedger, default_approval_ledger
from plotlot.harness.calculation_store import LocalCalculationLedger, default_calculation_ledger
from plotlot.harness.contracts import (
    ApprovalRequest,
    CalculationResult,
    Claim,
    EvidenceItem,
    JsonObject,
    MemoryItem,
    PlotLotEvent,
    Report,
    RunId,
    ToolCall,
    VerificationResult,
)
from plotlot.harness.contracts.base import HarnessContract
from plotlot.harness.evidence_store import LocalEvidenceLedger, default_evidence_ledger
from plotlot.harness.fixture_runs import FixtureDealRunResult
from plotlot.harness.memory_store import LocalMemoryStore, MemoryListFilter, default_memory_store
from plotlot.harness.report_store import LocalReportLedger, default_report_ledger
from plotlot.harness.run_store import (
    HarnessReplayBundle,
    LocalHarnessRunStore,
    default_harness_run_store,
)
from plotlot.harness.tool_call_store import LocalToolCallLedger, default_tool_call_ledger
from plotlot.harness.verification_store import LocalVerificationLedger, default_verification_ledger


@dataclass(frozen=True, slots=True)
class DebugBundleStores:
    run_store: LocalHarnessRunStore
    evidence_ledger: LocalEvidenceLedger
    report_ledger: LocalReportLedger
    calculation_ledger: LocalCalculationLedger
    verification_ledger: LocalVerificationLedger
    approval_ledger: LocalApprovalLedger
    memory_store: LocalMemoryStore
    tool_call_ledger: LocalToolCallLedger


class HarnessDebugBundle(HarnessContract):
    run: FixtureDealRunResult
    replay: HarnessReplayBundle
    events: list[PlotLotEvent]
    event_count: int = Field(ge=0)
    evidence: list[EvidenceItem]
    claims: list[Claim]
    calculations: list[CalculationResult]
    reports: list[Report]
    verifications: list[VerificationResult]
    approvals: list[ApprovalRequest]
    approval_events: list[PlotLotEvent]
    memory: list[MemoryItem]
    tool_calls: list[ToolCall]
    redactions: list[str]
    metadata: JsonObject = Field(default_factory=dict)


def export_debug_bundle(run_id: RunId, stores: DebugBundleStores) -> HarnessDebugBundle:
    run = stores.run_store.get_run(run_id)
    events = stores.run_store.get_events(run_id)
    return HarnessDebugBundle(
        run=run,
        replay=stores.run_store.replay_run(run_id),
        events=events,
        event_count=len(events),
        evidence=stores.evidence_ledger.list_evidence(run_id=run_id),
        claims=stores.report_ledger.list_claims(run_id=run_id),
        calculations=stores.calculation_ledger.list_calculations(run_id=run_id),
        reports=stores.report_ledger.list_reports(run_id=run_id),
        verifications=stores.verification_ledger.list_verifications(run_id=run_id),
        approvals=stores.approval_ledger.list_approvals(run_id=run_id),
        approval_events=stores.approval_ledger.list_events(run_id),
        memory=stores.memory_store.list_memory(MemoryListFilter(source_run_id=run_id)),
        tool_calls=stores.tool_call_ledger.list_tool_calls(run_id=run_id),
        redactions=["secrets_omitted", "full_transcripts_omitted"],
        metadata={
            "bundle_format": "plotlot.local_debug_bundle.v1",
            "source_mode": run.source_mode.value,
            "transcript_policy": "transcript artifacts are private and full text is omitted",
        },
    )


def default_debug_bundle_stores() -> DebugBundleStores:
    return DebugBundleStores(
        run_store=default_harness_run_store(),
        evidence_ledger=default_evidence_ledger(),
        report_ledger=default_report_ledger(),
        calculation_ledger=default_calculation_ledger(),
        verification_ledger=default_verification_ledger(),
        approval_ledger=default_approval_ledger(),
        memory_store=default_memory_store(),
        tool_call_ledger=default_tool_call_ledger(),
    )
