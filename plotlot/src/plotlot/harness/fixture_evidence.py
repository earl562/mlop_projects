from __future__ import annotations

from plotlot.harness.contracts import (
    ApplicabilityStatus,
    EvidenceId,
    EvidenceItem,
    EvidenceSourceType,
    FreshnessStatus,
)
from plotlot.harness.fixture_runs import FixtureDealRunResult


def fixture_evidence_for_run(result: FixtureDealRunResult) -> list[EvidenceItem]:
    return [
        EvidenceItem(
            evidence_id=EvidenceId(evidence_id),
            run_id=result.run_id,
            source_type=EvidenceSourceType.GIS_LAYER,
            source_name="South Florida GIS fixture evidence",
            source_url="fixture://south-florida-gis",
            source_identifier=evidence_id,
            provider="fixture",
            jurisdiction="South Florida",
            freshness_status=FreshnessStatus.FIXTURE,
            applicability=ApplicabilityStatus.REQUIRES_MUNICIPAL_VERIFICATION,
            normalized_text="Fixture GIS evidence for a preliminary PlotLot harness run.",
            structured_payload={
                "report_id": result.report_id,
                "verification_status": result.verification_status,
                "preliminary": result.preliminary,
            },
            confidence=0.5,
            source_mode=result.source_mode,
            metadata={"source_mode": result.source_mode.value},
        )
        for evidence_id in result.evidence_ids
    ]
