from __future__ import annotations

from plotlot.harness.contracts import JsonObject, Report, VerificationResult
from plotlot.harness.report_inspection import comp_support_snapshot, zoning_support_snapshot


def verification_payload(
    verification: VerificationResult,
    *,
    report: Report | None = None,
) -> JsonObject:
    payload = verification.model_dump(mode="json")
    payload["warning_checks"] = _checks_with_status(verification, status="warning")
    payload["blocked_checks"] = _checks_with_status(verification, status="blocked")
    payload["jurisdiction_alignment_status"] = str(
        verification.checks.get("jurisdiction_alignment") or "unknown"
    )
    payload["jurisdiction_mismatch_count"] = len(verification.jurisdiction_mismatches)
    snapshot = comp_support_snapshot(report)
    if snapshot:
        payload["comp_support_snapshot"] = snapshot
    zoning_snapshot = zoning_support_snapshot(report)
    if zoning_snapshot:
        payload["zoning_support_snapshot"] = zoning_snapshot
    return payload


def _checks_with_status(
    verification: VerificationResult,
    *,
    status: str,
) -> list[str]:
    checks = verification.checks
    return sorted(
        key
        for key, value in checks.items()
        if isinstance(key, str) and str(value).strip() == status
    )
