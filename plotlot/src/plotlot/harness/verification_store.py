from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from pydantic import Field

from plotlot.harness.contracts import ReportId, RunId, VerificationId, VerificationResult
from plotlot.harness.contracts.base import HarnessContract

VERIFICATION_STORE_PATH_ENV = "PLOTLOT_HARNESS_VERIFICATION_STORE_PATH"


@dataclass(frozen=True, slots=True)
class VerificationNotFoundError(Exception):
    lookup_id: str

    def __str__(self) -> str:
        return f"Harness verification not found: {self.lookup_id}"


class VerificationLedgerSnapshot(HarnessContract):
    verifications: dict[str, VerificationResult] = Field(default_factory=dict)


class LocalVerificationLedger:
    def __init__(self, path: Path) -> None:
        self._path = path

    def save_verification(self, result: VerificationResult) -> VerificationResult:
        snapshot = self._read_snapshot()
        verifications = dict(snapshot.verifications)
        verifications[str(result.verification_id)] = result
        self._write_snapshot(VerificationLedgerSnapshot(verifications=verifications))
        return result

    def list_verifications(self, *, run_id: RunId | None = None) -> list[VerificationResult]:
        verifications = self._read_snapshot().verifications.values()
        filtered = (
            verifications
            if run_id is None
            else [verification for verification in verifications if verification.run_id == run_id]
        )
        return sorted(
            filtered,
            key=lambda verification: (verification.created_at, str(verification.verification_id)),
        )

    def get_verification(self, verification_id: VerificationId) -> VerificationResult:
        verification = self._read_snapshot().verifications.get(str(verification_id))
        if verification is None:
            raise VerificationNotFoundError(lookup_id=str(verification_id))
        return verification

    def get_latest_for_report(self, report_id: ReportId) -> VerificationResult:
        verifications = [
            item
            for item in self._read_snapshot().verifications.values()
            if item.report_id == report_id
        ]
        if not verifications:
            raise VerificationNotFoundError(lookup_id=str(report_id))
        return sorted(verifications, key=lambda item: item.created_at)[-1]

    def _read_snapshot(self) -> VerificationLedgerSnapshot:
        if not self._path.exists():
            return VerificationLedgerSnapshot()
        raw = self._path.read_text(encoding="utf-8")
        if not raw.strip():
            return VerificationLedgerSnapshot()
        return VerificationLedgerSnapshot.model_validate_json(raw)

    def _write_snapshot(self, snapshot: VerificationLedgerSnapshot) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")


def default_verification_ledger_path() -> Path:
    configured = os.environ.get(VERIFICATION_STORE_PATH_ENV)
    if configured:
        return Path(configured).expanduser()
    state_home = os.environ.get("XDG_STATE_HOME")
    base = Path(state_home).expanduser() if state_home else Path.home() / ".local" / "state"
    return base / "plotlot" / "harness-verifications.json"


def default_verification_ledger() -> LocalVerificationLedger:
    return LocalVerificationLedger(default_verification_ledger_path())
