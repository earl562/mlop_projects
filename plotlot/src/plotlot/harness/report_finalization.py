from __future__ import annotations

from dataclasses import dataclass

from plotlot.harness.contracts import (
    Report,
    ReportId,
    ReportStatus,
    VerificationResult,
    VerificationStatus,
)
from plotlot.harness.contracts.base import utc_now
from plotlot.harness.report_store import LocalReportLedger
from plotlot.harness.verification_store import LocalVerificationLedger, VerificationNotFoundError


@dataclass(frozen=True, slots=True)
class ReportFinalizationBlockedError(Exception):
    report_id: ReportId
    verification: VerificationResult | None
    reason: str

    def __str__(self) -> str:
        return f"Report finalization blocked for {self.report_id}: {self.reason}"


def finalize_report(
    report_id: ReportId,
    *,
    report_ledger: LocalReportLedger,
    verification_ledger: LocalVerificationLedger,
) -> Report:
    report = report_ledger.get_report(report_id)
    try:
        verification = verification_ledger.get_latest_for_report(report_id)
    except VerificationNotFoundError as exc:
        raise ReportFinalizationBlockedError(
            report_id=report_id,
            verification=None,
            reason="missing_verification",
        ) from exc
    _raise_if_verification_blocks_finalization(report_id, verification)
    finalized = report.model_copy(update={"status": ReportStatus.FINAL, "finalized_at": utc_now()})
    report_ledger.save_report(finalized)
    return finalized


def _raise_if_verification_blocks_finalization(
    report_id: ReportId,
    verification: VerificationResult,
) -> None:
    if verification.status in {VerificationStatus.FAILED, VerificationStatus.BLOCKED}:
        raise ReportFinalizationBlockedError(
            report_id=report_id,
            verification=verification,
            reason=verification.status.value,
        )
    if verification.mock_or_fixture_blockers:
        raise ReportFinalizationBlockedError(
            report_id=report_id,
            verification=verification,
            reason="mock_or_fixture_evidence",
        )
    if _has_blocked_comping_underwriting_gate(verification):
        raise ReportFinalizationBlockedError(
            report_id=report_id,
            verification=verification,
            reason="comping_underwriting_not_ready",
        )
    if _has_weak_comp_support(verification):
        raise ReportFinalizationBlockedError(
            report_id=report_id,
            verification=verification,
            reason="weak_comp_support",
        )
    if _has_weak_comp_provenance(verification):
        raise ReportFinalizationBlockedError(
            report_id=report_id,
            verification=verification,
            reason="weak_comp_provenance",
        )
    if _has_weak_exit_market_support(verification):
        raise ReportFinalizationBlockedError(
            report_id=report_id,
            verification=verification,
            reason="weak_exit_market_support",
        )
    if _has_weak_zoning_official_support(verification):
        raise ReportFinalizationBlockedError(
            report_id=report_id,
            verification=verification,
            reason="weak_zoning_official_support",
        )


def _has_weak_comp_support(verification: VerificationResult) -> bool:
    comp_support = verification.checks.get("comp_support")
    return isinstance(comp_support, str) and comp_support == "warning"


def _has_blocked_comping_underwriting_gate(verification: VerificationResult) -> bool:
    comping_gate = verification.checks.get("comping_underwriting_gate")
    return isinstance(comping_gate, str) and comping_gate == "warning"


def _has_weak_exit_market_support(verification: VerificationResult) -> bool:
    exit_market_support = verification.checks.get("exit_market_support")
    return isinstance(exit_market_support, str) and exit_market_support == "warning"


def _has_weak_comp_provenance(verification: VerificationResult) -> bool:
    comp_provenance = verification.checks.get("comp_provenance")
    return isinstance(comp_provenance, str) and comp_provenance == "warning"


def _has_weak_zoning_official_support(verification: VerificationResult) -> bool:
    zoning_official_support = verification.checks.get("zoning_official_support")
    return isinstance(zoning_official_support, str) and zoning_official_support == "warning"
