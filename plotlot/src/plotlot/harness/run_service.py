"""Harness run service (Phase 6 — master spec §10).

Orchestrates the first paid feature: the zoning feasibility memo run.
create AnalysisRun → emit run_started → fetch zoning → record evidence →
build evidence-backed report → validate (reject uncited material claims) →
emit run_completed. Unknowns are explicit ("unknown / needs verification"),
never guessed. Deterministic enough to replay.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from plotlot.ingestion.events import HarnessEvent, HarnessEventType
from plotlot.reports.evidence_report_builder import EvidenceReportBuilder, ReportClaim


@dataclass
class RunRequest:
    """Master spec §10 POST /api/v1/harness/runs request."""

    workspace_id: str
    project_id: str
    site: dict
    skill_name: str
    intended_use: str
    assumptions: dict = field(default_factory=dict)


@dataclass
class RunResult:
    analysis_run_id: str
    status: str
    report_id: str
    evidence_ids: list[str]
    report_claims: list[ReportClaim]
    events: list[HarnessEvent]


def _ev(type_: HarnessEventType, run_id: str, severity: str, payload: dict) -> HarnessEvent:
    return HarnessEvent(type=type_, severity=severity, payload=payload, analysis_run_id=run_id)


async def start_run(
    req: RunRequest,
    *,
    fetch_zoning: Callable[[str], Awaitable[str | None]] | None = None,
) -> RunResult:
    """Run the zoning feasibility memo skill.

    fetch_zoning is injectable (provider-agnostic): (address) -> zoning_code | None.
    When None/returns None, the zoning claim is "unknown / needs verification"
    (never guessed — master spec rule #11).
    """
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    events: list[HarnessEvent] = []
    evidence_ids: list[str] = []
    claims: list[ReportClaim] = []

    events.append(
        _ev(
            HarnessEventType.RUN_REQUESTED,
            run_id,
            "info",
            {
                "analysis_run_id": run_id,
                "skill_name": req.skill_name,
                "site_id": req.site.get("address", ""),
                "intended_use": req.intended_use,
            },
        )
    )
    events.append(
        _ev(
            HarnessEventType.RUN_STARTED,
            run_id,
            "info",
            {"analysis_run_id": run_id, "model": "glm5.2"},
        )
    )

    address = req.site.get("address", "")
    zoning_code: str | None = None
    if fetch_zoning is not None:
        zoning_code = await fetch_zoning(address)

    # Zoning district claim — verified if evidence, else unknown (never guessed).
    if zoning_code:
        ev_id = f"ev_{uuid.uuid4().hex[:10]}"
        evidence_ids.append(ev_id)
        claims.append(
            ReportClaim(
                key="zoning.district",
                text=f"Zoning district: {zoning_code}",
                material=True,
                evidence_ids=[ev_id],
                confidence="high",
                source_caveat="Online code may not be official; verify with municipality.",
            )
        )
        events.append(
            _ev(
                HarnessEventType.EVIDENCE_RECORDED,
                run_id,
                "info",
                {
                    "evidence_id": ev_id,
                    "tool_run_id": "zoning_lookup",
                    "claim_key": "zoning.district",
                    "source_type": "gis_zoning",
                },
            )
        )
    else:
        # No evidence → unknown, needs_verification (master spec rule #11).
        claims.append(
            ReportClaim(
                key="zoning.district",
                text="Zoning district unknown / requires verification",
                material=False,
                evidence_ids=[],
                confidence="unknown",
                needs_verification=True,
                source_caveat="No verified zoning source; confirm with municipality.",
            )
        )

    # Intended-use permission claim (always needs ordinance verification).
    claims.append(
        ReportClaim(
            key=f"use_permission.{req.intended_use}",
            text=f"{req.intended_use} permission: requires ordinance use-table confirmation",
            material=True if zoning_code else False,
            evidence_ids=evidence_ids if zoning_code else [],
            confidence="medium" if zoning_code else "unknown",
            needs_verification=True,
        )
    )

    # Build + validate report (reject uncited material claims).
    builder = EvidenceReportBuilder(analysis_run_id=run_id, evidence_ids=evidence_ids)
    report = builder.build(claims)

    events.append(
        _ev(
            HarnessEventType.REPORT_COMPLETED,
            run_id,
            "info",
            {
                "report_id": report["report_id"],
                "analysis_run_id": run_id,
                "claim_count": len(report["claims"]),
                "uncited_count": report["uncited_count"],
            },
        )
    )

    status = "completed" if report["uncited_count"] == 0 else "needs_review"
    events.append(
        _ev(
            HarnessEventType.RUN_COMPLETED,
            run_id,
            "info",
            {
                "analysis_run_id": run_id,
                "report_id": report["report_id"],
                "duration_ms": 0,
            },
        )
    )

    return RunResult(
        analysis_run_id=run_id,
        status=status,
        report_id=report["report_id"],
        evidence_ids=evidence_ids,
        report_claims=claims,
        events=events,
    )


__all__ = ["RunRequest", "RunResult", "start_run"]
