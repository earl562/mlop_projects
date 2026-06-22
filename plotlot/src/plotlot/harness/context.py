from __future__ import annotations

from dataclasses import dataclass
from typing import assert_never

from plotlot.core.lookup_snapshot import (
    CalculationTrace,
    DisplayState,
    EvidenceId,
    FieldKey,
    FieldScalar,
    LookupField,
    LookupSnapshot,
)
from plotlot.harness.context_evidence import ContextEvidencePacket, context_evidence_packets
from plotlot.harness.context_quality import (
    stale_evidence_open_questions,
    stale_evidence_warnings,
)


@dataclass(frozen=True, slots=True)
class ContextFieldPacket:
    key: FieldKey
    label: str
    value: FieldScalar
    unit: str
    display_state: DisplayState
    evidence_ids: tuple[EvidenceId, ...]
    confidence: float
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ContextBuildRequest:
    workspace_id: str
    objective: str
    project_id: str | None = None
    site_id: str | None = None
    evidence_ids: tuple[EvidenceId, ...] = ()
    lookup_snapshot: LookupSnapshot | None = None
    open_questions: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ContextPacket:
    workspace_id: str
    project_id: str | None
    site_id: str | None
    objective: str
    evidence_ids: tuple[EvidenceId, ...]
    evidence_packets: tuple[ContextEvidencePacket, ...]
    fields: tuple[ContextFieldPacket, ...]
    calculations: tuple[CalculationTrace, ...]
    warnings: tuple[str, ...]
    open_questions: tuple[str, ...]


class ContextBroker:
    def build_packet(self, request: ContextBuildRequest) -> ContextPacket:
        snapshot = request.lookup_snapshot
        evidence_ids = _context_evidence_ids(request)
        fields = _context_fields(snapshot)
        evidence_packets = context_evidence_packets(snapshot, evidence_ids)
        warnings = _context_warnings(request, evidence_packets)
        open_questions = _context_open_questions(request, evidence_packets)

        return ContextPacket(
            workspace_id=request.workspace_id,
            project_id=request.project_id,
            site_id=request.site_id or _snapshot_site_id(snapshot),
            objective=request.objective,
            evidence_ids=evidence_ids,
            evidence_packets=evidence_packets,
            fields=fields,
            calculations=() if snapshot is None else snapshot.calculations,
            warnings=warnings,
            open_questions=open_questions,
        )


def _context_evidence_ids(request: ContextBuildRequest) -> tuple[EvidenceId, ...]:
    snapshot = request.lookup_snapshot
    snapshot_ids: tuple[EvidenceId, ...]
    if snapshot is None:
        snapshot_ids = ()
    else:
        snapshot_ids = _snapshot_evidence_ids(snapshot)
    return _unique_evidence((*request.evidence_ids, *snapshot_ids))


def _snapshot_evidence_ids(snapshot: LookupSnapshot) -> tuple[EvidenceId, ...]:
    evidence_ids: list[EvidenceId] = []
    for field in snapshot.fields:
        evidence_ids.extend(field.evidence_ids)
    for calculation in snapshot.calculations:
        evidence_ids.extend(calculation.input_evidence_ids)
    return _unique_evidence(tuple(evidence_ids))


def _context_fields(snapshot: LookupSnapshot | None) -> tuple[ContextFieldPacket, ...]:
    if snapshot is None:
        return ()
    return tuple(
        ContextFieldPacket(
            key=field.key,
            label=field.label,
            value=field.value,
            unit=field.unit,
            display_state=field.display_state,
            evidence_ids=field.evidence_ids,
            confidence=field.confidence,
            warnings=field.warnings,
        )
        for field in snapshot.fields
    )


def _context_warnings(
    request: ContextBuildRequest,
    evidence_packets: tuple[ContextEvidencePacket, ...],
) -> tuple[str, ...]:
    snapshot = request.lookup_snapshot
    snapshot_warnings: tuple[str, ...]
    field_warnings: tuple[str, ...]
    if snapshot is None:
        snapshot_warnings = ()
        field_warnings = ()
    else:
        snapshot_warnings = snapshot.warnings
        field_warnings = tuple(warning for field in snapshot.fields for warning in field.warnings)
    return _unique_strings(
        (
            *request.warnings,
            *snapshot_warnings,
            *field_warnings,
            *stale_evidence_warnings(evidence_packets),
        )
    )


def _context_open_questions(
    request: ContextBuildRequest,
    evidence_packets: tuple[ContextEvidencePacket, ...],
) -> tuple[str, ...]:
    snapshot = request.lookup_snapshot
    field_questions: tuple[str, ...]
    if snapshot is None:
        field_questions = ()
    else:
        field_questions = tuple(
            question
            for field in snapshot.fields
            for question in (_open_question_for_field(field),)
            if question is not None
        )
    return _unique_strings(
        (
            *request.open_questions,
            *field_questions,
            *stale_evidence_open_questions(evidence_packets),
        )
    )


def _open_question_for_field(field: LookupField) -> str | None:
    key = str(field.key)
    match field.display_state:
        case DisplayState.VERIFIED:
            return None
        case DisplayState.ASSUMED:
            return f"{key} is assumed; keep it separate from verified lookup facts."
        case DisplayState.STALE:
            return f"{key} is stale; refresh authoritative evidence before relying on it."
        case DisplayState.CONTRADICTED:
            return f"{key} is contradicted; surface sources for human review before use."
        case DisplayState.UNKNOWN:
            return f"{key} is unknown; retrieve authoritative evidence before use."
        case DisplayState.REQUIRES_HUMAN_REVIEW:
            return f"{key} requires human review before use."
        case unreachable:
            assert_never(unreachable)


def _snapshot_site_id(snapshot: LookupSnapshot | None) -> str | None:
    if snapshot is None:
        return None
    return str(snapshot.site_id)


def _unique_evidence(evidence_ids: tuple[EvidenceId, ...]) -> tuple[EvidenceId, ...]:
    seen: set[str] = set()
    unique: list[EvidenceId] = []
    for evidence_id in evidence_ids:
        value = str(evidence_id)
        if value in seen:
            continue
        seen.add(value)
        unique.append(evidence_id)
    return tuple(unique)


def _unique_strings(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return tuple(unique)
