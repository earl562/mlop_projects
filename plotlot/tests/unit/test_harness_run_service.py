"""Phase 6 TDD: harness run service + zoning feasibility memo (first paid feature).

Master spec §4 (first paid feature) + §10 (run service) + §12 (report builder)
+ §6 (analysis events). Tests written BEFORE implementation.
"""

from __future__ import annotations

import pytest

from plotlot.ingestion.events import HarnessEventType
from plotlot.harness.run_service import RunRequest, start_run
from plotlot.reports.evidence_report_builder import EvidenceReportBuilder, ReportClaim


async def _zoning_rs8(_addr: str) -> str | None:
    return "RS-8"


async def _zoning_none(_addr: str) -> str | None:
    return None


class TestRunService:
    """Master spec §10: POST /api/v1/harness/runs behavior."""

    @pytest.mark.asyncio
    async def test_run_creates_analysis_run_and_emits_started(self):
        req = RunRequest(
            workspace_id="ws_1",
            project_id="proj_1",
            site={"address": "1234 NW 15th St, Fort Lauderdale, FL 33311"},
            skill_name="zoning_feasibility_memo",
            intended_use="multifamily",
        )
        result = await start_run(req, fetch_zoning=_zoning_rs8)
        assert result.analysis_run_id
        assert result.status in ("completed", "needs_review")
        types = {e.type for e in result.events}
        assert HarnessEventType.RUN_STARTED.value in types
        assert HarnessEventType.RUN_COMPLETED.value in types

    @pytest.mark.asyncio
    async def test_run_records_evidence_and_report(self):
        req = RunRequest(
            workspace_id="ws_1",
            project_id="proj_1",
            site={"address": "1234 NW 15th St, Fort Lauderdale, FL 33311"},
            skill_name="zoning_feasibility_memo",
            intended_use="multifamily",
        )
        result = await start_run(req, fetch_zoning=_zoning_rs8)
        assert result.evidence_ids, "must record evidence"
        assert result.report_id

    @pytest.mark.asyncio
    async def test_unknown_zoning_emits_unknown_not_guess(self):
        req = RunRequest(
            workspace_id="ws_1",
            project_id="proj_1",
            site={"address": "Unknown Address, FL"},
            skill_name="zoning_feasibility_memo",
            intended_use="multifamily",
        )
        result = await start_run(req, fetch_zoning=_zoning_none)
        assert any(c.needs_verification for c in result.report_claims)


class TestEvidenceReportBuilder:
    """Master spec §12: reject uncited material claims."""

    def test_rejects_material_claim_without_evidence(self):
        builder = EvidenceReportBuilder(analysis_run_id="run_1", evidence_ids=["ev_1", "ev_2"])
        uncited = ReportClaim(
            key="zoning.district", text="RS-8", material=True, evidence_ids=[], confidence="high"
        )
        rejected = builder.validate_claims([uncited])
        assert "zoning.district" in rejected

    def test_accepts_cited_material_claim(self):
        builder = EvidenceReportBuilder(analysis_run_id="run_1", evidence_ids=["ev_1"])
        cited = ReportClaim(
            key="zoning.district",
            text="RS-8",
            material=True,
            evidence_ids=["ev_1"],
            confidence="high",
        )
        rejected = builder.validate_claims([cited])
        assert "zoning.district" not in rejected

    def test_accepts_unknown_non_material_claim_without_evidence(self):
        builder = EvidenceReportBuilder(analysis_run_id="run_1", evidence_ids=[])
        unknown = ReportClaim(
            key="overlay.risk",
            text="unknown",
            material=False,
            evidence_ids=[],
            confidence="unknown",
            needs_verification=True,
        )
        rejected = builder.validate_claims([unknown])
        assert "overlay.risk" not in rejected

    def test_rejects_evidence_from_wrong_run(self):
        builder = EvidenceReportBuilder(analysis_run_id="run_1", evidence_ids=["ev_1"])
        bad = ReportClaim(
            key="zoning.district",
            text="RS-8",
            material=True,
            evidence_ids=["ev_OUTSIDE"],
            confidence="high",
        )
        rejected = builder.validate_claims([bad])
        assert "zoning.district" in rejected
