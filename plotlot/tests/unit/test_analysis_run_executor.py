"""Unit tests for POST /api/v1/analysis-runs/{run_id}/execute endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from plotlot.api.main import app
from plotlot.api.middleware import rate_limiter
from plotlot.pipeline.skills.registry import HandlerResult
from plotlot.storage.models import AnalysisRun


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    rate_limiter.reset()
    yield
    rate_limiter.reset()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _mock_session_with_run(run: AnalysisRun, *, assumption_set=None):
    """Build an AsyncMock session that returns the given AnalysisRun on get() and execute()."""
    session = AsyncMock()

    async def _get_side_effect(model, key):
        model_name = getattr(model, "__name__", "")
        if model_name == "AnalysisRun":
            return run
        if model_name == "AssumptionSet":
            return assumption_set
        return None

    session.get = AsyncMock(side_effect=_get_side_effect)

    run_result = MagicMock()
    run_result.scalar_one_or_none = MagicMock(return_value=run)
    as_result = MagicMock()
    as_result.scalar_one_or_none = MagicMock(return_value=assumption_set)

    async def _execute_side_effect(stmt):
        stmt_str = str(stmt).lower()
        if "assumption_sets" in stmt_str or "assumptionset" in stmt_str:
            return as_result
        return run_result

    session.execute = AsyncMock(side_effect=_execute_side_effect)
    return session


@pytest.mark.asyncio
async def test_pending_to_completed(client):
    """Execute a pending AnalysisRun — handler succeeds, status transitions to completed."""
    run = AnalysisRun(
        id="run-1",
        workspace_id="ws-1",
        project_id="prj-1",
        site_id="site-1",
        analysis_id="analysis-1",
        skill_name="single_parcel_feasibility",
        status="pending",
        input_json={"zoning_report": {}, "county": "Miami-Dade", "state": "FL", "land_purchase_price": 300000},
        output_json={},
    )

    mock_handler = AsyncMock(
        return_value=HandlerResult(
            output_json={"max_units": 6, "max_offer_price": 308580},
            evidence_ids=["ev-1"],
        )
    )

    mock_persist_result = MagicMock()
    mock_persist_result.status = "ok"
    mock_persist_result.message = None
    mock_persist_result.artifact_ids = {"report_id": "rpt-1"}
    mock_persist_result.result_payload = {"artifacts": {}}

    session = _mock_session_with_run(run)

    with (
        patch("plotlot.api.analyses.get_session", new=AsyncMock(return_value=session)),
        patch("plotlot.api.analyses.get_handler", return_value=mock_handler),
        patch("plotlot.api.analyses.persist_tool_artifacts", new=AsyncMock(return_value=mock_persist_result)),
    ):
        resp = await client.post("/api/v1/analysis-runs/run-1/execute")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "completed"
        assert body["output_json"] == {"max_units": 6, "max_offer_price": 308580}
        assert body["started_at"] is not None
        assert body["completed_at"] is not None


@pytest.mark.asyncio
async def test_handler_error_transitions_to_failed(client):
    """Handler raises an exception — status transitions to failed with error_message."""
    run = AnalysisRun(
        id="run-2",
        workspace_id="ws-1",
        project_id="prj-1",
        site_id="site-1",
        analysis_id=None,
        skill_name="single_parcel_feasibility",
        status="pending",
        input_json={"county": "Miami-Dade"},
        output_json={},
    )

    mock_handler = AsyncMock(side_effect=RuntimeError("simulated calculation failure"))

    session = _mock_session_with_run(run)

    with (
        patch("plotlot.api.analyses.get_session", new=AsyncMock(return_value=session)),
        patch("plotlot.api.analyses.get_handler", return_value=mock_handler),
    ):
        resp = await client.post("/api/v1/analysis-runs/run-2/execute")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "failed"
        assert "simulated calculation failure" in body["error_message"]


@pytest.mark.asyncio
async def test_409_if_not_pending(client):
    """Return 409 Conflict when the AnalysisRun is not in pending status."""
    run = AnalysisRun(
        id="run-3",
        workspace_id="ws-1",
        project_id="prj-1",
        site_id="site-1",
        analysis_id="analysis-1",
        skill_name="single_parcel_feasibility",
        status="completed",
        input_json={},
        output_json={"max_units": 4},
    )

    session = _mock_session_with_run(run)

    with patch("plotlot.api.analyses.get_session", new=AsyncMock(return_value=session)):
        resp = await client.post("/api/v1/analysis-runs/run-3/execute")
        assert resp.status_code == 409
