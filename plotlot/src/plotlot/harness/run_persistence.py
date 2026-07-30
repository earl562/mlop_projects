from __future__ import annotations

from dataclasses import dataclass

from plotlot.harness.calculation_store import LocalCalculationLedger, default_calculation_ledger
from plotlot.harness.evidence_store import LocalEvidenceLedger, default_evidence_ledger
from plotlot.harness.fixture_evidence import fixture_evidence_for_run
from plotlot.harness.fixture_reports import fixture_claims_for_run, fixture_report_for_run
from plotlot.harness.fixture_runs import FixtureDealRunResult
from plotlot.harness.report_store import LocalReportLedger, default_report_ledger
from plotlot.harness.run_store import LocalHarnessRunStore, default_harness_run_store
from plotlot.harness.tool_call_store import LocalToolCallLedger, default_tool_call_ledger
from plotlot.harness.verification import verify_report_traceability
from plotlot.harness.verification_store import LocalVerificationLedger, default_verification_ledger


@dataclass(frozen=True, slots=True)
class FixtureRunPersistenceStores:
    run_store: LocalHarnessRunStore
    evidence_ledger: LocalEvidenceLedger
    calculation_ledger: LocalCalculationLedger | None = None
    tool_call_ledger: LocalToolCallLedger | None = None
    report_ledger: LocalReportLedger | None = None
    verification_ledger: LocalVerificationLedger | None = None


def persist_fixture_run_result(
    result: FixtureDealRunResult,
    stores: FixtureRunPersistenceStores,
) -> FixtureDealRunResult:
    stores.run_store.save_run(result)
    evidence_items = result.evidence_items or fixture_evidence_for_run(result)
    claims = result.claims or fixture_claims_for_run(result)
    if stores.report_ledger is not None:
        claim_ids = [str(claim.claim_id) for claim in claims]
        evidence_items = [
            item.model_copy(update={"linked_claim_ids": claim_ids}) for item in evidence_items
        ]
    for item in evidence_items:
        stores.evidence_ledger.save_evidence(item)
    if stores.calculation_ledger is not None:
        for calculation in result.calculations:
            stores.calculation_ledger.save_calculation(calculation)
    if stores.tool_call_ledger is not None:
        for tool_call in result.tool_calls:
            stores.tool_call_ledger.save_tool_call(tool_call)
    if stores.report_ledger is not None:
        report = result.report or fixture_report_for_run(result, claims)
        stores.report_ledger.save_claims(claims)
        stores.report_ledger.save_report(report)
        if stores.verification_ledger is not None:
            stores.verification_ledger.save_verification(
                verify_report_traceability(report, claims, evidence_items)
            )
    return result


def default_fixture_run_persistence_stores() -> FixtureRunPersistenceStores:
    return FixtureRunPersistenceStores(
        run_store=default_harness_run_store(),
        evidence_ledger=default_evidence_ledger(),
        calculation_ledger=default_calculation_ledger(),
        tool_call_ledger=default_tool_call_ledger(),
        report_ledger=default_report_ledger(),
        verification_ledger=default_verification_ledger(),
    )
