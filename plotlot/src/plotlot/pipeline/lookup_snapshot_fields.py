from __future__ import annotations

from plotlot.core.lookup_snapshot import (
    ContradictionStatus,
    EvidenceId,
    FailureBehavior,
    FieldKey,
    FieldQuality,
    FieldScalar,
    FreshnessStatus,
    LookupField,
    LookupFieldSpec,
)


def parcel_field(
    key: str,
    label: str,
    value: FieldScalar,
    unit: str,
    evidence_ids: tuple[EvidenceId, ...],
) -> LookupField:
    return _field(
        key,
        label,
        value,
        unit,
        evidence_ids if has_value(value) else (),
        ("official_assessor", "county_parcel_gis"),
        ("third_party_parcel_aggregator",),
        1.0,
    )


def zoning_field(
    key: str,
    label: str,
    value: FieldScalar,
    unit: str,
    evidence_ids: tuple[EvidenceId, ...],
) -> LookupField:
    return _field(
        key,
        label,
        value,
        unit,
        evidence_ids if has_value(value) else (),
        ("official_zoning_map", "official_zoning_ordinance", "adopted_planning_pdf"),
        ("official_assessor",),
        0.92,
    )


def calculation_field(
    key: str,
    label: str,
    value: FieldScalar,
    unit: str,
    evidence_ids: tuple[EvidenceId, ...],
) -> LookupField:
    return _field(
        key,
        label,
        value,
        unit,
        evidence_ids if has_value(value) else (),
        ("deterministic_calculator",),
        ("human_review",),
        1.0,
    )


def has_value(value: FieldScalar) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, int | float):
        return value > 0
    return value


def _field(
    key: str,
    label: str,
    value: FieldScalar,
    unit: str,
    evidence_ids: tuple[EvidenceId, ...],
    source_priority: tuple[str, ...],
    fallback_sources: tuple[str, ...],
    parser_confidence: float,
) -> LookupField:
    freshness = FreshnessStatus.CURRENT if evidence_ids else FreshnessStatus.UNKNOWN
    quality = FieldQuality(
        accepted_authority=bool(evidence_ids),
        freshness=freshness,
        units_normalized=True,
        parser_confidence=parser_confidence if evidence_ids else 0.0,
        contradiction_status=ContradictionStatus.CLEAR,
    )
    return LookupField.from_quality(
        LookupFieldSpec(
            key=FieldKey(key),
            label=label,
            value=value,
            unit=unit,
            evidence_ids=evidence_ids,
            source_priority=source_priority,
            fallback_sources=fallback_sources,
            failure_behavior=FailureBehavior.UNKNOWN,
        ),
        quality,
    )
