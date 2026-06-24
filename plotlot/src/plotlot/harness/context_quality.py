from __future__ import annotations

from typing import Protocol

from plotlot.core.lookup_snapshot import EvidenceId, FieldKey
from plotlot.pipeline.lookup_snapshot_source_quality import STALE_SOURCE_FLAG


class EvidenceQualityPacket(Protocol):
    @property
    def evidence_id(self) -> EvidenceId: ...

    @property
    def referenced_field_keys(self) -> tuple[FieldKey, ...]: ...

    @property
    def quality_flags(self) -> tuple[str, ...]: ...


def stale_evidence_warnings(
    evidence_packets: tuple[EvidenceQualityPacket, ...],
) -> tuple[str, ...]:
    return tuple(STALE_SOURCE_FLAG for packet in evidence_packets if _is_stale(packet))


def stale_evidence_open_questions(
    evidence_packets: tuple[EvidenceQualityPacket, ...],
) -> tuple[str, ...]:
    return tuple(
        _stale_evidence_question(packet) for packet in evidence_packets if _is_stale(packet)
    )


def _is_stale(packet: EvidenceQualityPacket) -> bool:
    return STALE_SOURCE_FLAG in packet.quality_flags


def _stale_evidence_question(packet: EvidenceQualityPacket) -> str:
    field_keys = ", ".join(str(key) for key in packet.referenced_field_keys)
    target = field_keys or "unmapped lookup fields"
    return (
        f"{packet.evidence_id} is stale; refresh authoritative evidence before relying on {target}."
    )
