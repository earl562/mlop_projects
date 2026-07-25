from __future__ import annotations

from collections.abc import Sequence

from plotlot.harness.contracts import (
    ApplicabilityStatus,
    Claim,
    ClaimFreshnessStatus,
    ClaimKind,
    ClaimOrigin,
    EvidenceItem,
    EvidenceSourceType,
    FreshnessStatus,
    Report,
    SourceMode,
    VerificationId,
    VerificationResult,
    VerificationStatus,
)
from plotlot.harness.report_inspection import comp_support_summary, underwriting_mode, zoning_support_summary


def verify_report_traceability(
    report: Report,
    claims: Sequence[Claim],
    evidence_items: Sequence[EvidenceItem],
) -> VerificationResult:
    evidence_by_id = {str(item.evidence_id): item for item in evidence_items}
    missing_evidence = _missing_evidence_ids(claims, evidence_by_id)
    claim_boundary_errors = _claim_boundary_error_ids(claims)
    unsupported_claims = _unsupported_claim_ids(claims)
    stale_evidence = _stale_evidence_ids(evidence_items)
    jurisdiction_mismatches = _jurisdiction_mismatch_ids(claims, evidence_by_id)
    mock_or_fixture_blockers = _mock_or_fixture_blockers(report, evidence_items)
    checks = {
        "claim_evidence": "passed" if not missing_evidence and not unsupported_claims else "failed",
        "claim_source_boundary": "failed" if claim_boundary_errors else "passed",
        "source_mode": "blocked" if mock_or_fixture_blockers else "passed",
        "freshness": "warning" if stale_evidence else "passed",
        "underwriting_basis": _underwriting_basis_check(report),
        "comping_underwriting_gate": _comping_underwriting_gate_check(report),
        "comp_support": _comp_support_check(report),
        "comp_provenance": _comp_provenance_check(report, evidence_items),
        "exit_market_support": _exit_market_support_check(report),
        "zoning_official_support": _zoning_official_support_check(report),
        "jurisdiction_alignment": "warning" if jurisdiction_mismatches else "passed",
    }
    return VerificationResult(
        verification_id=VerificationId(f"verification_{report.report_id}"),
        run_id=report.run_id,
        report_id=report.report_id,
        status=_verification_status(
            missing_evidence=missing_evidence,
            unsupported_claims=unsupported_claims,
            mock_or_fixture_blockers=mock_or_fixture_blockers,
            has_warnings=_has_warning_checks(checks),
        ),
        checks=checks,
        missing_evidence=missing_evidence,
        stale_evidence=stale_evidence,
        unsupported_claims=unsupported_claims,
        jurisdiction_mismatches=jurisdiction_mismatches,
        mock_or_fixture_blockers=mock_or_fixture_blockers,
    )


def _missing_evidence_ids(
    claims: Sequence[Claim],
    evidence_by_id: dict[str, EvidenceItem],
) -> list[str]:
    missing: list[str] = []
    for claim in claims:
        for evidence_id in claim.evidence_ids:
            evidence_key = str(evidence_id)
            if evidence_key not in evidence_by_id:
                missing.append(evidence_key)
    return sorted(set(missing))


def _unsupported_claim_ids(claims: Sequence[Claim]) -> list[str]:
    unsupported: list[str] = []
    for claim in claims:
        if _claim_has_support(claim) and not _claim_boundary_errors(claim):
            continue
        unsupported.append(str(claim.claim_id))
    return unsupported


def _claim_boundary_error_ids(claims: Sequence[Claim]) -> list[str]:
    return [str(claim.claim_id) for claim in claims if _claim_boundary_errors(claim)]


def _claim_has_support(claim: Claim) -> bool:
    return bool(
        claim.evidence_ids
        or claim.calculation_ids
        or claim.assumption_ids
        or claim.transcript_segment_ids
        or claim.training_concept_ids
    )


def _claim_boundary_errors(claim: Claim) -> list[str]:
    errors: list[str] = []
    if claim.kind == ClaimKind.HYPOTHESIS and not claim.next_verification_step.strip():
        errors.append("hypothesis_missing_next_verification_step")
    if claim.origin in {ClaimOrigin.LOCAL_AUTHORITY, ClaimOrigin.GIS_PROVIDER}:
        if not claim.source_url.strip():
            errors.append("authority_claim_missing_source_url")
    if claim.kind == ClaimKind.VERIFIED_FACT and claim.claim_freshness in {
        ClaimFreshnessStatus.STALE,
        ClaimFreshnessStatus.UNKNOWN,
        ClaimFreshnessStatus.REQUIRES_OFFICIAL_VERIFICATION,
    }:
        errors.append("verified_fact_has_unverified_freshness")
    return errors


def _stale_evidence_ids(evidence_items: Sequence[EvidenceItem]) -> list[str]:
    stale_statuses = {
        FreshnessStatus.STALE,
        FreshnessStatus.UNKNOWN,
        FreshnessStatus.REQUIRES_OFFICIAL_VERIFICATION,
    }
    return sorted(
        str(item.evidence_id)
        for item in evidence_items
        if item.freshness_status in stale_statuses
    )


def _jurisdiction_mismatch_ids(
    claims: Sequence[Claim],
    evidence_by_id: dict[str, EvidenceItem],
) -> list[str]:
    mismatches: list[str] = []
    for claim in claims:
        if not _is_zoning_claim(claim):
            continue
        zoning_evidence = [
            item
            for evidence_id in claim.evidence_ids
            if (item := evidence_by_id.get(str(evidence_id))) is not None
            and item.source_type in _ZONING_EVIDENCE_TYPES
        ]
        if not zoning_evidence:
            continue
        if any(item.applicability is ApplicabilityStatus.DIRECT for item in zoning_evidence):
            continue
        if any(item.applicability in _NON_DIRECT_APPLICABILITY for item in zoning_evidence):
            mismatches.append(str(claim.claim_id))
    return sorted(set(mismatches))


def _mock_or_fixture_blockers(report: Report, evidence_items: Sequence[EvidenceItem]) -> list[str]:
    blockers: list[str] = []
    seen: set[str] = set()
    for item in evidence_items:
        if item.source_mode not in {SourceMode.FIXTURE, SourceMode.MOCK} and item.freshness_status not in {
            FreshnessStatus.FIXTURE,
            FreshnessStatus.MOCK,
        }:
            continue
        evidence_id = str(item.evidence_id)
        if evidence_id in seen:
            continue
        seen.add(evidence_id)
        blockers.append(evidence_id)
    if blockers:
        return blockers
    if report.source_mode in {SourceMode.FIXTURE, SourceMode.MOCK}:
        return [str(report.report_id)]
    return []


def _verification_status(
    *,
    missing_evidence: list[str],
    unsupported_claims: list[str],
    mock_or_fixture_blockers: list[str],
    has_warnings: bool,
) -> VerificationStatus:
    if mock_or_fixture_blockers:
        return VerificationStatus.BLOCKED
    if missing_evidence or unsupported_claims:
        return VerificationStatus.FAILED
    if has_warnings:
        return VerificationStatus.PASSED_WITH_WARNINGS
    return VerificationStatus.PASSED


def _underwriting_basis_check(report: Report) -> str:
    mode = str(underwriting_mode(report).get("mode") or "").strip()
    if mode in {"sold_unit_exit", "missing_income_inputs"}:
        return "warning"
    return "passed"


def _comp_support_check(report: Report) -> str:
    summary = comp_support_summary(report)
    status = str(summary.get("status") or "").strip()
    combined_support_tier = str(summary.get("combined_support_tier") or "").strip()
    land_market_scope = str(summary.get("land_support_market_scope") or "").strip()
    land_micro_market_confidence = str(summary.get("land_micro_market_confidence") or "").strip()
    parse_confidence = summary.get("land_support_parse_confidence")
    if (
        status == "warning"
        or combined_support_tier in {"exit_only", "weak"}
        or land_market_scope == "cross_zip_same_municipality"
    ):
        return "warning"
    if land_micro_market_confidence in {"low", "unknown"}:
        return "warning"
    if isinstance(parse_confidence, int | float) and float(parse_confidence) < 0.8:
        return "warning"
    return "passed"


def _comping_underwriting_gate_check(report: Report) -> str:
    summary = comp_support_summary(report)
    status = str(summary.get("comping_underwriting_status") or "").strip()
    if status in {"", "unknown", "available_to_underwriting"}:
        return "passed"
    return "warning"


def _exit_market_support_check(report: Report) -> str:
    summary = comp_support_summary(report)
    market_scope = str(summary.get("exit_support_market_scope") or "").strip()
    recency_tier = str(summary.get("exit_support_recency_tier") or "").strip()
    micro_market_confidence = str(summary.get("exit_micro_market_confidence") or "").strip()
    quality_score = summary.get("exit_support_quality_score")
    distance_miles = summary.get("exit_support_distance_miles")
    if market_scope and market_scope not in {"subject_municipality", "subject_zip"}:
        return "warning"
    if isinstance(distance_miles, int | float) and float(distance_miles) > 1.5:
        return "warning"
    if recency_tier in {"unknown", "extended_24m", "stale"}:
        return "warning"
    if isinstance(quality_score, int | float) and float(quality_score) < 0.7:
        return "warning"
    if micro_market_confidence in {"low", "unknown"}:
        return "warning"
    return "passed"


def _comp_provenance_check(report: Report, evidence_items: Sequence[EvidenceItem]) -> str:
    if report.source_mode is not SourceMode.LIVE:
        return "passed"
    tiers = {
        str(item.metadata.get("provenance_tier") or "").strip()
        for item in evidence_items
        if item.source_type in {EvidenceSourceType.MARKET_COMP, EvidenceSourceType.RENTAL_COMP}
    }
    if not tiers:
        return "passed"
    accepted_tiers = {"official_record", "public_listing_county_reconciled"}
    if tiers.issubset(accepted_tiers):
        return "passed"
    return "warning"


def _zoning_official_support_check(report: Report) -> str:
    summary = zoning_support_summary(report)
    status = str(summary.get("status") or "").strip()
    if status == "warning":
        return "warning"
    if bool(summary.get("requires_official_verification")):
        return "warning"
    if not bool(summary.get("ordinance_rules_resolved")):
        return "warning"
    if not bool(summary.get("authority_is_official")):
        return "warning"
    if report.source_mode is SourceMode.LIVE and not bool(summary.get("authority_is_live")):
        return "warning"
    if str(summary.get("authority_confidence") or "").strip() in {
        "staged_preliminary",
        "unknown",
    }:
        return "warning"
    if str(summary.get("gis_applicability") or "").strip() == "requires_municipal_verification":
        return "warning"
    return "passed"


def _has_warning_checks(checks: dict[str, str]) -> bool:
    return any(value == "warning" for value in checks.values())


def _is_zoning_claim(claim: Claim) -> bool:
    field_key = str(claim.field_key or "").strip()
    return field_key.startswith("zoning.") or claim.claim_type in {
        "zoning_code",
        "manual_dimensional_standards",
    }


_ZONING_EVIDENCE_TYPES = {
    EvidenceSourceType.ZONING_BOUNDARY,
    EvidenceSourceType.ORDINANCE_TEXT,
    EvidenceSourceType.MUNICODE_SECTION,
    EvidenceSourceType.GIS_LAYER,
}

_NON_DIRECT_APPLICABILITY = {
    ApplicabilityStatus.CONTEXTUAL,
    ApplicabilityStatus.NOT_APPLICABLE,
    ApplicabilityStatus.REQUIRES_MUNICIPAL_VERIFICATION,
    ApplicabilityStatus.UNKNOWN,
}
