from __future__ import annotations

from typing import Final

from plotlot.core.lookup_snapshot import (
    ContradictionStatus,
    EvidenceId,
    FailureBehavior,
    FieldKey,
    FieldQuality,
    FreshnessStatus,
    LookupField,
    LookupFieldSpec,
)
from plotlot.core.types import ZoningReport
from plotlot.pipeline.lookup_snapshot_fields import zoning_field

CONTRADICTORY_SOURCES_WARNING: Final = "contradictory_sources"


def zoning_district_field(
    report: ZoningReport,
    parcel_evidence_ids: tuple[EvidenceId, ...],
    ordinance_evidence_ids: tuple[EvidenceId, ...],
) -> LookupField:
    if _has_zoning_contradiction(report) and parcel_evidence_ids and ordinance_evidence_ids:
        return _contradicted_zoning_district_field(
            report,
            (*ordinance_evidence_ids, *parcel_evidence_ids),
        )
    return zoning_field(
        "zoning.district",
        "Zoning district",
        report.zoning_district,
        "",
        ordinance_evidence_ids,
    )


def _contradicted_zoning_district_field(
    report: ZoningReport,
    evidence_ids: tuple[EvidenceId, ...],
) -> LookupField:
    return LookupField.from_quality(
        LookupFieldSpec(
            key=FieldKey("zoning.district"),
            label="Zoning district",
            value=report.zoning_district,
            unit="",
            evidence_ids=evidence_ids,
            source_priority=("official_zoning_map", "official_zoning_ordinance"),
            fallback_sources=("official_assessor",),
            failure_behavior=FailureBehavior.ESCALATE,
            warnings=(CONTRADICTORY_SOURCES_WARNING,),
        ),
        FieldQuality(
            accepted_authority=True,
            freshness=FreshnessStatus.CURRENT,
            units_normalized=True,
            parser_confidence=0.92,
            contradiction_status=ContradictionStatus.BLOCKING,
        ),
    )


def _has_zoning_contradiction(report: ZoningReport) -> bool:
    parcel_zoning = _parcel_zoning_code(report)
    official_zoning = _normalized_zoning(report.zoning_district)
    return bool(parcel_zoning and official_zoning and parcel_zoning != official_zoning)


def _parcel_zoning_code(report: ZoningReport) -> str:
    if report.property_record is None:
        return ""
    return _normalized_zoning(report.property_record.zoning_code)


def _normalized_zoning(value: str) -> str:
    return " ".join(value.upper().split())
