from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum, unique
from typing import Final, NewType, assert_never

EvidenceId = NewType("EvidenceId", str)
FieldKey = NewType("FieldKey", str)
LookupSnapshotId = NewType("LookupSnapshotId", str)
RunId = NewType("RunId", str)
SiteId = NewType("SiteId", str)

type FieldScalar = str | int | float | bool | None

MIN_DISPLAY_PARSER_CONFIDENCE: Final = 0.8
MISSING_EVIDENCE_WARNING: Final = "missing_evidence"


@unique
class DisplayState(StrEnum):
    VERIFIED = "verified"
    ASSUMED = "assumed"
    STALE = "stale"
    CONTRADICTED = "contradicted"
    UNKNOWN = "unknown"
    REQUIRES_HUMAN_REVIEW = "requires_human_review"


@unique
class FreshnessStatus(StrEnum):
    CURRENT = "current"
    STALE = "stale"
    UNKNOWN = "unknown"


@unique
class ContradictionStatus(StrEnum):
    CLEAR = "clear"
    WARNING = "warning"
    BLOCKING = "blocking"


@unique
class FailureBehavior(StrEnum):
    UNKNOWN = "unknown"
    WARN = "warn"
    ESCALATE = "escalate"
    REFUSE = "refuse"


@dataclass(frozen=True, slots=True)
class FieldQuality:
    accepted_authority: bool
    freshness: FreshnessStatus
    units_normalized: bool
    parser_confidence: float
    contradiction_status: ContradictionStatus

    def confidence(self, has_evidence: bool) -> float:
        source_score = 1.0 if has_evidence else 0.0
        authority_score = 1.0 if self.accepted_authority else 0.0
        unit_score = 1.0 if self.units_normalized else 0.0
        return min(
            source_score,
            authority_score,
            unit_score,
            self.parser_confidence,
            _freshness_score(self.freshness),
            _contradiction_score(self.contradiction_status),
        )

    def display_state(self, has_evidence: bool) -> DisplayState:
        if not has_evidence:
            return DisplayState.UNKNOWN

        match self.contradiction_status:
            case ContradictionStatus.BLOCKING:
                return DisplayState.CONTRADICTED
            case ContradictionStatus.CLEAR | ContradictionStatus.WARNING:
                pass
            case unreachable_contradiction:
                assert_never(unreachable_contradiction)

        match self.freshness:
            case FreshnessStatus.CURRENT:
                pass
            case FreshnessStatus.STALE:
                return DisplayState.STALE
            case FreshnessStatus.UNKNOWN:
                return DisplayState.UNKNOWN
            case unreachable_freshness:
                assert_never(unreachable_freshness)

        if not self.accepted_authority:
            return DisplayState.REQUIRES_HUMAN_REVIEW
        if not self.units_normalized:
            return DisplayState.REQUIRES_HUMAN_REVIEW
        if self.parser_confidence < MIN_DISPLAY_PARSER_CONFIDENCE:
            return DisplayState.REQUIRES_HUMAN_REVIEW
        return DisplayState.VERIFIED


@dataclass(frozen=True, slots=True)
class LookupFieldSpec:
    key: FieldKey
    label: str
    value: FieldScalar
    unit: str
    evidence_ids: tuple[EvidenceId, ...]
    source_priority: tuple[str, ...]
    fallback_sources: tuple[str, ...]
    failure_behavior: FailureBehavior = FailureBehavior.UNKNOWN
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LookupField:
    key: FieldKey
    label: str
    value: FieldScalar
    unit: str
    display_state: DisplayState
    evidence_ids: tuple[EvidenceId, ...]
    source_priority: tuple[str, ...]
    fallback_sources: tuple[str, ...]
    failure_behavior: FailureBehavior
    confidence: float
    freshness: FreshnessStatus
    warnings: tuple[str, ...]

    @classmethod
    def from_quality(cls, spec: LookupFieldSpec, quality: FieldQuality) -> LookupField:
        has_evidence = bool(spec.evidence_ids)
        warnings = _with_missing_evidence_warning(spec.warnings, has_evidence)
        return cls(
            key=spec.key,
            label=spec.label,
            value=spec.value,
            unit=spec.unit,
            display_state=quality.display_state(has_evidence),
            evidence_ids=spec.evidence_ids,
            source_priority=spec.source_priority,
            fallback_sources=spec.fallback_sources,
            failure_behavior=spec.failure_behavior,
            confidence=quality.confidence(has_evidence),
            freshness=quality.freshness,
            warnings=warnings,
        )

    @property
    def is_display_ready(self) -> bool:
        match self.display_state:
            case DisplayState.VERIFIED:
                return bool(self.evidence_ids)
            case (
                DisplayState.ASSUMED
                | DisplayState.STALE
                | DisplayState.CONTRADICTED
                | DisplayState.UNKNOWN
                | DisplayState.REQUIRES_HUMAN_REVIEW
            ):
                return False
            case unreachable:
                assert_never(unreachable)


@dataclass(frozen=True, slots=True)
class CalculationTrace:
    calculator_name: str
    calculator_version: str
    formula: str
    input_evidence_ids: tuple[EvidenceId, ...]
    output_label: str
    warnings: tuple[str, ...]

    @property
    def is_reproducible(self) -> bool:
        return bool(self.input_evidence_ids)


@dataclass(frozen=True, slots=True)
class EvidenceSourceMetadata:
    evidence_id: EvidenceId
    source_url: str
    source_title: str
    source_type: str = ""
    source_authority: str = ""
    publisher: str = ""
    retrieved_at: str = ""
    effective_date: str = ""
    parser_version: str = ""
    schema_version: str = ""
    raw_artifact_ref: str = ""
    query_parameters: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LookupSnapshot:
    lookup_snapshot_id: LookupSnapshotId
    site_id: SiteId
    run_id: RunId
    fields: tuple[LookupField, ...]
    calculations: tuple[CalculationTrace, ...]
    warnings: tuple[str, ...]
    source_metadata: tuple[EvidenceSourceMetadata, ...] = ()

    def evidence_ids_for(self, key: FieldKey) -> tuple[EvidenceId, ...]:
        for field in self.fields:
            if field.key == key:
                return field.evidence_ids
        return ()

    def source_metadata_for(self, evidence_id: EvidenceId) -> EvidenceSourceMetadata | None:
        for metadata in self.source_metadata:
            if metadata.evidence_id == evidence_id:
                return metadata
        return None


def _freshness_score(status: FreshnessStatus) -> float:
    match status:
        case FreshnessStatus.CURRENT:
            return 1.0
        case FreshnessStatus.STALE:
            return 0.5
        case FreshnessStatus.UNKNOWN:
            return 0.0
        case unreachable:
            assert_never(unreachable)


def _contradiction_score(status: ContradictionStatus) -> float:
    match status:
        case ContradictionStatus.CLEAR:
            return 1.0
        case ContradictionStatus.WARNING:
            return 0.5
        case ContradictionStatus.BLOCKING:
            return 0.0
        case unreachable:
            assert_never(unreachable)


def _with_missing_evidence_warning(
    warnings: tuple[str, ...],
    has_evidence: bool,
) -> tuple[str, ...]:
    if has_evidence:
        return warnings
    if MISSING_EVIDENCE_WARNING in warnings:
        return warnings
    return (*warnings, MISSING_EVIDENCE_WARNING)
