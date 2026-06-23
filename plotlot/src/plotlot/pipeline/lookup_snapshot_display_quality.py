from __future__ import annotations

from dataclasses import replace
from typing import Protocol, assert_never

from plotlot.core.lookup_snapshot import (
    DisplayState,
    EvidenceId,
    FreshnessStatus,
    LookupField,
    LookupSnapshot,
)
from plotlot.pipeline.lookup_snapshot_source_quality import STALE_SOURCE_FLAG
from plotlot.pipeline.lookup_snapshot_source_quality import (
    ASSUMPTION_SOURCE_FLAGS,
    SOURCE_QUALITY_BLOCKING_FLAGS,
)


class EvidenceQualityRecord(Protocol):
    @property
    def evidence_id(self) -> EvidenceId: ...

    @property
    def quality_flags(self) -> tuple[str, ...]: ...

    @property
    def quality_score(self) -> float: ...


def apply_source_quality_to_snapshot(
    snapshot: LookupSnapshot,
    evidence_records: tuple[EvidenceQualityRecord, ...],
) -> LookupSnapshot:
    quality_by_id = {record.evidence_id: record for record in evidence_records}
    if not quality_by_id:
        return snapshot
    return replace(
        snapshot,
        fields=tuple(_field_with_source_quality(field, quality_by_id) for field in snapshot.fields),
        warnings=_unique_strings(
            (
                *snapshot.warnings,
                *(
                    flag
                    for record in evidence_records
                    for flag in record.quality_flags
                    if _snapshot_warning_flag(flag)
                ),
            )
        ),
    )


def _field_with_source_quality(
    field: LookupField,
    quality_by_id: dict[EvidenceId, EvidenceQualityRecord],
) -> LookupField:
    records = tuple(
        quality_by_id[evidence_id]
        for evidence_id in field.evidence_ids
        if evidence_id in quality_by_id
    )
    if not records:
        return field
    quality_flags = _unique_strings(
        tuple(flag for record in records for flag in record.quality_flags)
    )
    display_flags = _display_affecting_flags(quality_flags)
    if not display_flags:
        return field
    warnings = _unique_strings((*field.warnings, *display_flags))
    confidence = min((field.confidence, *(record.quality_score for record in records)))
    if ASSUMPTION_SOURCE_FLAGS.intersection(display_flags):
        return _field_with_assumption_source_quality(field, warnings, confidence)
    if SOURCE_QUALITY_BLOCKING_FLAGS.intersection(display_flags):
        return _field_with_review_required_source_quality(field, warnings, confidence)
    if STALE_SOURCE_FLAG in display_flags:
        return _field_with_stale_source_quality(field, warnings, confidence)
    return replace(field, warnings=warnings, confidence=confidence)


def _field_with_assumption_source_quality(
    field: LookupField,
    warnings: tuple[str, ...],
    confidence: float,
) -> LookupField:
    match field.display_state:
        case DisplayState.VERIFIED | DisplayState.STALE | DisplayState.REQUIRES_HUMAN_REVIEW:
            return replace(
                field,
                display_state=DisplayState.ASSUMED,
                confidence=confidence,
                warnings=warnings,
            )
        case DisplayState.ASSUMED:
            return replace(field, confidence=confidence, warnings=warnings)
        case DisplayState.CONTRADICTED | DisplayState.UNKNOWN:
            return replace(field, warnings=warnings)
        case unreachable:
            assert_never(unreachable)


def _field_with_review_required_source_quality(
    field: LookupField,
    warnings: tuple[str, ...],
    confidence: float,
) -> LookupField:
    match field.display_state:
        case DisplayState.VERIFIED | DisplayState.STALE:
            return replace(
                field,
                display_state=DisplayState.REQUIRES_HUMAN_REVIEW,
                confidence=confidence,
                warnings=warnings,
            )
        case DisplayState.REQUIRES_HUMAN_REVIEW | DisplayState.ASSUMED:
            return replace(field, confidence=confidence, warnings=warnings)
        case DisplayState.CONTRADICTED | DisplayState.UNKNOWN:
            return replace(field, warnings=warnings)
        case unreachable:
            assert_never(unreachable)


def _field_with_stale_source_quality(
    field: LookupField,
    warnings: tuple[str, ...],
    confidence: float,
) -> LookupField:
    match field.display_state:
        case DisplayState.VERIFIED | DisplayState.STALE:
            return replace(
                field,
                display_state=DisplayState.STALE,
                freshness=FreshnessStatus.STALE,
                confidence=confidence,
                warnings=warnings,
            )
        case (
            DisplayState.ASSUMED
            | DisplayState.CONTRADICTED
            | DisplayState.UNKNOWN
            | DisplayState.REQUIRES_HUMAN_REVIEW
        ):
            return replace(field, warnings=warnings)
        case unreachable:
            assert_never(unreachable)


def _snapshot_warning_flag(flag: str) -> bool:
    return (
        flag == STALE_SOURCE_FLAG
        or flag in SOURCE_QUALITY_BLOCKING_FLAGS
        or flag in ASSUMPTION_SOURCE_FLAGS
    )


def _display_affecting_flags(quality_flags: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(flag for flag in quality_flags if _snapshot_warning_flag(flag))


def _unique_strings(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return tuple(unique)
