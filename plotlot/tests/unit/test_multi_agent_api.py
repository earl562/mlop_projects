from __future__ import annotations

from fastapi import APIRouter, FastAPI
from httpx import ASGITransport, AsyncClient

from plotlot.harness.agents import (
    AgentPlan,
    MultiAgentRunResult,
    MultiAgentRunStatus,
)
from plotlot.api.agent_runs import get_multi_agent_coordinator, router


class FakeCoordinator:
    def __init__(self):
        self.context = None
        self.request = None

    def plan(self, request):
        self.request = request
        return AgentPlan(
            workflow=request.workflow,
            objective=request.objective,
            tasks=(),
        )

    async def run(self, request, context):
        self.request = request
        self.context = context
        plan = self.plan(request)
        return MultiAgentRunResult(
            run_id=context.run_id,
            workflow=request.workflow,
            status=MultiAgentRunStatus.COMPLETED,
            plan=plan,
            task_results=(),
            agents=(),
        )


def _app(fake: FakeCoordinator) -> FastAPI:
    app = FastAPI()
    parent = APIRouter(prefix="/api/v1/harness/jobs")
    parent.include_router(router)
    app.include_router(parent)
    app.dependency_overrides[get_multi_agent_coordinator] = lambda: fake
    return app


async def test_agent_registry_endpoint_lists_specialists():
    app = _app(FakeCoordinator())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/v1/harness/jobs/agent-runs/specialists")

    assert response.status_code == 200
    names = {item["name"] for item in response.json()}
    assert names == {
        "site_identity",
        "zoning_research",
        "feasibility",
        "underwriting",
        "sourcing",
        "reporting",
    }


async def test_plan_endpoint_is_side_effect_free():
    fake = FakeCoordinator()
    app = _app(fake)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/harness/jobs/agent-runs/plan",
            json={
                "workflow": "site_feasibility",
                "objective": "Analyze the parcel",
                "address": "123 Main St",
            },
        )

    assert response.status_code == 200
    assert response.json()["workflow"] == "site_feasibility"
    assert fake.context is None


async def test_execute_endpoint_builds_governed_context():
    fake = FakeCoordinator()
    app = _app(fake)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/harness/jobs/agent-runs",
            json={
                "workflow": "lead_sourcing",
                "objective": "Find vacant land",
                "market": {"county": "Broward", "state": "FL"},
                "workspace_id": "ws_1",
                "project_id": "project_1",
                "risk_budget_cents": 75,
                "live_network_allowed": False,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["run_id"].startswith("run_")
    assert fake.context.workspace_id == "ws_1"
    assert fake.context.project_id == "project_1"
    assert fake.context.risk_budget_cents == 75
    assert fake.context.live_network_allowed is False
    assert fake.context.actor_user_id == "anonymous"


async def test_execute_endpoint_validates_workflow_scope():
    app = _app(FakeCoordinator())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/harness/jobs/agent-runs",
            json={
                "workflow": "site_feasibility",
                "objective": "Analyze it",
            },
        )

    assert response.status_code == 422


async def test_execute_endpoint_accepts_only_durable_workspace_approvals(monkeypatch):
    from types import SimpleNamespace

    fake = FakeCoordinator()
    app = _app(fake)

    class FakeSession:
        async def get(self, _model, approval_id):
            rows = {
                "apr_ok": SimpleNamespace(
                    workspace_id="ws_1",
                    status="approved",
                    expires_at=None,
                ),
                "apr_wrong_workspace": SimpleNamespace(
                    workspace_id="ws_other",
                    status="approved",
                    expires_at=None,
                ),
            }
            return rows.get(approval_id)

        async def close(self):
            return None

    async def fake_get_session():
        return FakeSession()

    monkeypatch.setattr("plotlot.storage.db.get_session", fake_get_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/harness/jobs/agent-runs",
            json={
                "workflow": "lead_sourcing",
                "objective": "Find vacant land",
                "market": {"county": "Broward", "state": "FL"},
                "workspace_id": "ws_1",
                "approved_approval_ids": ["apr_ok", "apr_wrong_workspace", "apr_missing"],
            },
        )

    assert response.status_code == 200
    assert fake.context.approved_approval_ids == {"apr_ok"}


async def test_execute_endpoint_fails_closed_when_approval_storage_is_unavailable(monkeypatch):
    fake = FakeCoordinator()
    app = _app(fake)

    async def broken_get_session():
        raise RuntimeError("database offline")

    monkeypatch.setattr("plotlot.storage.db.get_session", broken_get_session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/harness/jobs/agent-runs",
            json={
                "workflow": "lead_sourcing",
                "objective": "Find vacant land",
                "market": {"county": "Broward", "state": "FL"},
                "approved_approval_ids": ["apr_claimed"],
            },
        )

    assert response.status_code == 200
    assert fake.context.approved_approval_ids == set()
