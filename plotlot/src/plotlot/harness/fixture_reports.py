from __future__ import annotations

from pydantic import JsonValue

from plotlot.harness.contracts import (
    Claim,
    ClaimFreshnessStatus,
    ClaimId,
    ClaimKind,
    ClaimOrigin,
    ClaimStatus,
    EvidenceId,
    Report,
    ReportId,
    ReportStatus,
    ReportType,
)
from plotlot.harness.fixture_runs import FixtureDealRunResult


def fixture_claims_for_run(result: FixtureDealRunResult) -> list[Claim]:
    report_id = ReportId(result.report_id)
    evidence_ids = [EvidenceId(evidence_id) for evidence_id in result.evidence_ids]
    return [
        Claim(
            claim_id=ClaimId(f"claim_{result.run_id}_source_grounding"),
            run_id=result.run_id,
            report_id=report_id,
            claim_text="Fixture analysis is grounded in South Florida GIS fixture evidence.",
            claim_type="source_grounding",
            field_key="gis.fixture_source_grounding",
            kind=ClaimKind.CAVEAT,
            origin=ClaimOrigin.GIS_PROVIDER,
            status=ClaimStatus.PRELIMINARY,
            confidence=0.5,
            evidence_ids=evidence_ids,
            source_url="https://gis-mdc.opendata.arcgis.com/",
            next_verification_step=(
                "Replace fixture GIS evidence with live official source results before closing."
            ),
            claim_freshness=ClaimFreshnessStatus.FIXTURE,
            metadata={"source_boundary": "fixture_gis_context"},
            source_mode=result.source_mode,
        ),
        Claim(
            claim_id=ClaimId(f"claim_{result.run_id}_official_verification"),
            run_id=result.run_id,
            report_id=report_id,
            claim_text="Municipal zoning and GIS applicability require official verification before closing.",
            claim_type="official_verification_caveat",
            field_key="zoning.official_verification_required",
            kind=ClaimKind.HYPOTHESIS,
            origin=ClaimOrigin.LOCAL_AUTHORITY,
            status=ClaimStatus.NEEDS_VERIFICATION,
            confidence=0.5,
            evidence_ids=evidence_ids,
            source_url="https://library.municode.com/fl",
            next_verification_step=(
                "Verify controlling municipal zoning code, GIS applicability, and effective dates "
                "with the local planning department."
            ),
            claim_freshness=ClaimFreshnessStatus.REQUIRES_OFFICIAL_VERIFICATION,
            metadata={"source_boundary": "local_authority_required"},
            source_mode=result.source_mode,
        ),
    ]


def fixture_report_for_run(result: FixtureDealRunResult, claims: list[Claim]) -> Report:
    claim_ids = [claim.claim_id for claim in claims]
    section_claim_ids: list[JsonValue] = []
    for claim_id in claim_ids:
        section_claim_ids.append(str(claim_id))
    section_evidence_ids: list[JsonValue] = []
    for evidence_id in result.evidence_ids:
        section_evidence_ids.append(evidence_id)
    return Report(
        report_id=ReportId(result.report_id),
        run_id=result.run_id,
        report_type=_report_type_for_analysis(result.analysis_type),
        title=f"Preliminary {result.analysis_type.replace('_', ' ').title()}",
        status=ReportStatus.PRELIMINARY,
        sections=[
            {
                "section_id": "executive_summary",
                "title": "Executive Summary",
                "claim_ids": section_claim_ids,
            },
            {
                "section_id": "evidence_appendix",
                "title": "Evidence Appendix",
                "evidence_ids": section_evidence_ids,
            },
        ],
        claims=claim_ids,
        evidence_ids=[EvidenceId(evidence_id) for evidence_id in result.evidence_ids],
        source_mode=result.source_mode,
    )


def _report_type_for_analysis(analysis_type: str) -> ReportType:
    normalized = analysis_type.replace("-", "_")
    if normalized == "zoning_research":
        return ReportType.ZONING_RESEARCH_MEMO
    if normalized == "lender_package":
        return ReportType.LENDER_PACKAGE
    if normalized == "construction_budget":
        return ReportType.CONSTRUCTION_BUDGET
    return ReportType.ACQUISITION_MEMO
