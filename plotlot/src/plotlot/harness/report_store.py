from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from pydantic import Field

from plotlot.harness.contracts import Claim, ClaimId, Report, ReportId, RunId
from plotlot.harness.contracts.base import HarnessContract

REPORT_STORE_PATH_ENV = "PLOTLOT_HARNESS_REPORT_STORE_PATH"


@dataclass(frozen=True, slots=True)
class ClaimNotFoundError(Exception):
    claim_id: ClaimId

    def __str__(self) -> str:
        return f"Harness claim not found: {self.claim_id}"


@dataclass(frozen=True, slots=True)
class ReportNotFoundError(Exception):
    report_id: ReportId

    def __str__(self) -> str:
        return f"Harness report not found: {self.report_id}"


class ReportLedgerSnapshot(HarnessContract):
    claims: dict[str, Claim] = Field(default_factory=dict)
    reports: dict[str, Report] = Field(default_factory=dict)


class LocalReportLedger:
    def __init__(self, path: Path) -> None:
        self._path = path

    def save_claim(self, claim: Claim) -> Claim:
        snapshot = self._read_snapshot()
        claims = dict(snapshot.claims)
        claims[str(claim.claim_id)] = claim
        self._write_snapshot(ReportLedgerSnapshot(claims=claims, reports=snapshot.reports))
        return claim

    def save_claims(self, claims: list[Claim]) -> list[Claim]:
        snapshot = self._read_snapshot()
        next_claims = dict(snapshot.claims)
        for claim in claims:
            next_claims[str(claim.claim_id)] = claim
        self._write_snapshot(ReportLedgerSnapshot(claims=next_claims, reports=snapshot.reports))
        return claims

    def list_claims(self, *, run_id: RunId | None = None) -> list[Claim]:
        claims = self._read_snapshot().claims.values()
        filtered = (
            claims if run_id is None else [claim for claim in claims if claim.run_id == run_id]
        )
        return sorted(filtered, key=lambda claim: (claim.created_at, str(claim.claim_id)))

    def get_claim(self, claim_id: ClaimId) -> Claim:
        claim = self._read_snapshot().claims.get(str(claim_id))
        if claim is None:
            raise ClaimNotFoundError(claim_id=claim_id)
        return claim

    def save_report(self, report: Report) -> Report:
        snapshot = self._read_snapshot()
        reports = dict(snapshot.reports)
        reports[str(report.report_id)] = report
        self._write_snapshot(ReportLedgerSnapshot(claims=snapshot.claims, reports=reports))
        return report

    def list_reports(self, *, run_id: RunId | None = None) -> list[Report]:
        reports = self._read_snapshot().reports.values()
        filtered = (
            reports if run_id is None else [report for report in reports if report.run_id == run_id]
        )
        return sorted(filtered, key=lambda report: (report.generated_at, str(report.report_id)))

    def get_report(self, report_id: ReportId) -> Report:
        report = self._read_snapshot().reports.get(str(report_id))
        if report is None:
            raise ReportNotFoundError(report_id=report_id)
        return report

    def _read_snapshot(self) -> ReportLedgerSnapshot:
        if not self._path.exists():
            return ReportLedgerSnapshot()
        raw = self._path.read_text(encoding="utf-8")
        if not raw.strip():
            return ReportLedgerSnapshot()
        return ReportLedgerSnapshot.model_validate_json(raw)

    def _write_snapshot(self, snapshot: ReportLedgerSnapshot) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(snapshot.model_dump_json(indent=2), encoding="utf-8")


def default_report_ledger_path() -> Path:
    configured = os.environ.get(REPORT_STORE_PATH_ENV)
    if configured:
        return Path(configured).expanduser()
    state_home = os.environ.get("XDG_STATE_HOME")
    base = Path(state_home).expanduser() if state_home else Path.home() / ".local" / "state"
    return base / "plotlot" / "harness-reports.json"


def default_report_ledger() -> LocalReportLedger:
    return LocalReportLedger(default_report_ledger_path())
