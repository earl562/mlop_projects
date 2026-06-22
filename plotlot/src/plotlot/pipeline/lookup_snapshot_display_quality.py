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


class EvidenceQualityRecord(Protocol):
    @property
    def evidence_id(self) -> EvidenceId: ...

    @property
    def quality_flags(self) -> tuple[str, ...]: ...


def apply_source_quality_to_snapshot(
    snapshot: LookupSnapshot,
    evidence_records: tuple[EvidenceQualityRecord, ...],
) -> LookupSnapshot:
    stale_ids = frozenset(
        record.evidence_id
        for record in evidence_records
        if STALE_SOURCE_FLAG in record.quality_flags
    )
    if not stale_ids:
        return snapshot
    return replace(
        snapshot,
        fields=tuple(_field_with_source_quality(field, stale_ids) for field in snapshot.fields),
        warnings=_unique_strings((*snapshot.warnings, STALE_SOURCE_FLAG)),
    )


def _field_with_source_quality(
    field: LookupField,
    stale_ids: frozenset[EvidenceId],
) -> LookupField:
    if not stale_ids.intersection(field.evidence_ids):
        return field
    warnings = _unique_strings((*field.warnings, STALE_SOURCE_FLAG))
    match field.display_state:
        case DisplayState.VERIFIED | DisplayState.STALE:
            return replace(
                field,
                display_state=DisplayState.STALE,
                freshness=FreshnessStatus.STALE,
                confidence=min(field.confidence, 0.5),
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


def _unique_strings(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return tuple(unique)
