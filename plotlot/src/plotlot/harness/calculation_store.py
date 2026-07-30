from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import Field, field_validator

from plotlot.harness.contracts import CalculationResult, RunId
from plotlot.harness.contracts.base import HarnessContract, utc_now

CALCULATION_STORE_PATH_ENV = "PLOTLOT_HARNESS_CALCULATION_STORE_PATH"


@dataclass(frozen=True, slots=True)
class CalculationNotFoundError(Exception):
    calculation_id: str

    def __str__(self) -> str:
        return f"Calculation not found: {self.calculation_id}"


class StoredCalculation(HarnessContract):
    result: CalculationResult
    saved_at: datetime = Field(default_factory=utc_now)

    @field_validator("saved_at")
    @classmethod
    def _saved_at_must_be_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("saved_at must be timezone-aware")
        return value


class CalculationLedgerSnapshot(HarnessContract):
    calculations: dict[str, StoredCalculation] = Field(default_factory=dict)


class LocalCalculationLedger:
    def __init__(self, path: Path) -> None:
        self._path = path

    def save_calculation(self, result: CalculationResult) -> CalculationResult:
        snapshot = self._read_snapshot()
        calculations = dict(snapshot.calculations)
        calculations[result.calculation_id] = StoredCalculation(result=result)
        self._write_snapshot(CalculationLedgerSnapshot(calculations=calculations))
        return result

    def get_calculation(self, calculation_id: str) -> CalculationResult:
        snapshot = self._read_snapshot()
        stored = snapshot.calculations.get(calculation_id)
        if stored is None:
            raise CalculationNotFoundError(calculation_id=calculation_id)
        return stored.result

    def list_calculations(self, run_id: RunId | None = None) -> list[CalculationResult]:
        snapshot = self._read_snapshot()
        stored = sorted(
            snapshot.calculations.values(),
            key=lambda item: (item.result.created_at, item.result.calculation_id),
        )
        if run_id is None:
            return [item.result for item in stored]
        return [item.result for item in stored if item.result.run_id == run_id]

    def _read_snapshot(self) -> CalculationLedgerSnapshot:
        if not self._path.exists():
            return CalculationLedgerSnapshot()
        raw = self._path.read_text(encoding="utf-8")
        if not raw.strip():
            return CalculationLedgerSnapshot()
        return CalculationLedgerSnapshot.model_validate_json(raw)

    def _write_snapshot(self, snapshot: CalculationLedgerSnapshot) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")


def default_calculation_ledger_path() -> Path:
    configured = os.environ.get(CALCULATION_STORE_PATH_ENV)
    if configured:
        return Path(configured).expanduser()
    state_home = os.environ.get("XDG_STATE_HOME")
    base = Path(state_home).expanduser() if state_home else Path.home() / ".local" / "state"
    return base / "plotlot" / "harness-calculations.json"


def default_calculation_ledger() -> LocalCalculationLedger:
    return LocalCalculationLedger(default_calculation_ledger_path())
