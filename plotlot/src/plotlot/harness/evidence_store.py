from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import Field, field_validator

from plotlot.harness.contracts import EvidenceId, EvidenceItem, RunId
from plotlot.harness.contracts.base import HarnessContract, utc_now

EVIDENCE_STORE_PATH_ENV = "PLOTLOT_HARNESS_EVIDENCE_STORE_PATH"


@dataclass(frozen=True, slots=True)
class EvidenceNotFoundError(Exception):
    evidence_id: EvidenceId

    def __str__(self) -> str:
        return f"Evidence not found: {self.evidence_id}"


class StoredEvidence(HarnessContract):
    item: EvidenceItem
    saved_at: datetime = Field(default_factory=utc_now)

    @field_validator("saved_at")
    @classmethod
    def _saved_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("saved_at must be timezone-aware")
        return value


class EvidenceLedgerSnapshot(HarnessContract):
    evidence: dict[str, StoredEvidence] = Field(default_factory=dict)


class LocalEvidenceLedger:
    def __init__(self, path: Path) -> None:
        self._path = path

    def save_evidence(self, item: EvidenceItem) -> EvidenceItem:
        snapshot = self._read_snapshot()
        evidence = dict(snapshot.evidence)
        evidence[str(item.evidence_id)] = StoredEvidence(item=item)
        self._write_snapshot(EvidenceLedgerSnapshot(evidence=evidence))
        return item

    def get_evidence(self, evidence_id: EvidenceId) -> EvidenceItem:
        snapshot = self._read_snapshot()
        stored = snapshot.evidence.get(str(evidence_id))
        if stored is None:
            raise EvidenceNotFoundError(evidence_id=evidence_id)
        return stored.item

    def list_evidence(self, run_id: RunId | None = None) -> list[EvidenceItem]:
        snapshot = self._read_snapshot()
        stored = sorted(
            snapshot.evidence.values(),
            key=lambda item: (item.item.retrieved_at, item.item.evidence_id),
        )
        if run_id is None:
            return [item.item for item in stored]
        return [item.item for item in stored if item.item.run_id == run_id]

    def _read_snapshot(self) -> EvidenceLedgerSnapshot:
        if not self._path.exists():
            return EvidenceLedgerSnapshot()
        raw = self._path.read_text(encoding="utf-8")
        if not raw.strip():
            return EvidenceLedgerSnapshot()
        return EvidenceLedgerSnapshot.model_validate_json(raw)

    def _write_snapshot(self, snapshot: EvidenceLedgerSnapshot) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")


def default_evidence_ledger_path() -> Path:
    configured = os.environ.get(EVIDENCE_STORE_PATH_ENV)
    if configured:
        return Path(configured).expanduser()
    state_home = os.environ.get("XDG_STATE_HOME")
    base = Path(state_home).expanduser() if state_home else Path.home() / ".local" / "state"
    return base / "plotlot" / "harness-evidence.json"


def default_evidence_ledger() -> LocalEvidenceLedger:
    return LocalEvidenceLedger(default_evidence_ledger_path())
