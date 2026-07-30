"""Unit tests for REST tool surfaces and MCP equivalence."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


class FakeSession:
    def __init__(self):
        self.added = []
        self.committed = False
        self.rolled_back = False

    async def get(self, model, key):  # noqa: ANN001
        for obj in reversed(self.added):
            if isinstance(obj, model) and getattr(obj, "id", None) == key:
                return obj
        return None

    def add(self, obj):  # noqa: ANN001
        self.added.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_list_tools_returns_contracts(client):
    resp = await client.get("/api/v1/tools")
    assert resp.status_code == 200
    data = resp.json()
    names = {t["name"] for t in data}
    assert "geocode_address" in names
    assert "search_municode_live" in names
    assert "create_document" in names
    assert "create_spreadsheet" in names
    assert "export_dataset" in names


@pytest.mark.asyncio
async def test_tools_call_geocode_matches_mcp_adapter(client):
    from plotlot.harness.default_runtime import get_default_runtime
    from plotlot.harness.mcp_adapter import MCPAdapter
    from plotlot.land_use.models import ToolContext

    fake_session = FakeSession()

    async def _fake_geocode(address: str):
        return {
            "formatted_address": address,
            "municipality": "Example",
            "county": "Example",
            "state": "FL",
            "lat": 1.23,
            "lng": 4.56,
        }

    with (
        patch("plotlot.api.tools.get_session", new=AsyncMock(return_value=fake_session)),
        patch("plotlot.retrieval.geocode.geocode_address", new=_fake_geocode),
    ):
        # REST
        run_id = "run_test_1"
        resp = await client.post(
            "/api/v1/tools/call",
            json={
                "tool_name": "geocode_address",
                "arguments": {"address": "123 Main St"},
                "workspace_id": "ws_test",
                "run_id": run_id,
            },
        )
        assert resp.status_code == 200
        rest = resp.json()
        assert rest["status"] == "ok"
        assert rest["result"]["status"] == "success"
        assert rest["result"]["result"]["municipality"] == "Example"

        # MCP
        runtime = get_default_runtime()
        adapter = MCPAdapter(runtime)
        mcp_result = await adapter.call_tool(
            name="geocode_address",
            arguments={"address": "123 Main St"},
            context=ToolContext(
                workspace_id="ws_test",
                actor_user_id="anonymous",
                run_id=run_id,
                project_id="prj_test",
                risk_budget_cents=0,
            ),
        )
        assert mcp_result.status == "ok"
        assert mcp_result.result is not None
        assert mcp_result.result["status"] == "success"
        assert mcp_result.result["result"]["municipality"] == "Example"


@pytest.mark.asyncio
async def test_tools_call_search_ordinances_returns_normalized_results(client):
    from plotlot.core.types import SearchResult

    fake_session = FakeSession()

    async def _fake_hybrid_search(session, municipality, zone_code, limit=10, embedding=None):  # noqa: ANN001
        return [
            SearchResult(
                section="Sec. 47-18",
                section_title="Setback requirements",
                zone_codes=["RS-8"],
                chunk_text="Minimum front setback 25 feet. Rear setback 15 feet.",
                score=0.99,
                municipality=municipality,
                chunk_id=123,
                chapter="Chapter 47",
                municode_node_id="NODE_1",
                source_url="https://example.com/ordinance",
            )
        ]

    with (
        patch("plotlot.api.tools.get_session", new=AsyncMock(return_value=fake_session)),
        patch("plotlot.storage.db.get_session", new=AsyncMock(return_value=fake_session)),
        patch(
            "plotlot.retrieval.search.hybrid_search", new=AsyncMock(side_effect=_fake_hybrid_search)
        ),
    ):
        resp = await client.post(
            "/api/v1/tools/call",
            json={
                "tool_name": "search_ordinances",
                "arguments": {"municipality": "Example", "query": "RS-8 setbacks", "limit": 1},
                "workspace_id": "ws_test",
                "run_id": "run_test_search_ordinances",
            },
        )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "ok"
    assert payload["result"]["status"] == "success"
    assert payload["result"]["results"]
    first = payload["result"]["results"][0]
    assert first["heading"] == "Setback requirements"
    assert first["citation"]["url"] == "https://example.com/ordinance"


@pytest.mark.asyncio
async def test_tools_call_expensive_read_requires_approval(client):
    fake_session = FakeSession()
    with patch("plotlot.api.tools.get_session", new=AsyncMock(return_value=fake_session)):
        resp = await client.post(
            "/api/v1/tools/call",
            json={
                "tool_name": "search_municode_live",
                "arguments": {"municipality": "Example", "query": "parking"},
                "workspace_id": "ws_test",
                "risk_budget_cents": 0,
                "live_network_allowed": True,
                "run_id": "run_test_2",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending_approval"
    assert data["decision"]["approval_required"] is True
    assert data["decision"]["approval_id"]


@pytest.mark.asyncio
async def test_tools_call_search_zoning_ordinance_records_evidence_and_matches_mcp(client):
    from plotlot.core.types import SearchResult
    from plotlot.harness.default_runtime import get_default_runtime
    from plotlot.harness.mcp_adapter import MCPAdapter
    from plotlot.land_use.models import ToolContext

    fake_api_session = FakeSession()
    fake_search_session = FakeSession()

    async def _fake_hybrid_search(
        session, municipality: str, zone_code: str, limit: int = 10, embedding=None
    ):
        assert municipality == "Example City"
        assert zone_code == "parking"
        return [
            SearchResult(
                section="33-123",
                section_title="Off-street parking",
                zone_codes=["R-1"],
                chunk_text="Two spaces per dwelling unit.",
                score=0.99,
                municipality=municipality,
            )
        ]

    async def _fake_get_session_for_search():
        return fake_search_session

    with (
        patch("plotlot.api.tools.get_session", new=AsyncMock(return_value=fake_api_session)),
        patch("plotlot.storage.db.get_session", new=_fake_get_session_for_search),
        patch("plotlot.harness.ordinance_lookup.get_session", new=_fake_get_session_for_search),
        patch("plotlot.harness.ordinance_lookup.hybrid_search", new=_fake_hybrid_search),
    ):
        run_id = "run_test_4"
        resp = await client.post(
            "/api/v1/tools/call",
            json={
                "tool_name": "search_zoning_ordinance",
                "arguments": {"municipality": "Example City", "query": "parking"},
                "workspace_id": "ws_test",
                "run_id": run_id,
            },
        )
        assert resp.status_code == 200
        rest = resp.json()
        assert rest["status"] == "ok"
        assert rest["result"]["status"] == "success"
        assert rest["evidence_ids"]
        assert rest["result"]["results"][0]["evidence_id"] in set(rest["evidence_ids"])

        runtime = get_default_runtime()
        adapter = MCPAdapter(runtime)
        mcp_result = await adapter.call_tool(
            name="search_zoning_ordinance",
            arguments={"municipality": "Example City", "query": "parking"},
            context=ToolContext(
                workspace_id="ws_test",
                actor_user_id="anonymous",
                run_id=run_id,
                project_id="prj_test",
                risk_budget_cents=0,
            ),
        )
        assert mcp_result.status == "ok"
        assert mcp_result.result is not None
        assert mcp_result.result["status"] == "success"
        assert mcp_result.result["results"][0]["section"] == "33-123"


@pytest.mark.asyncio
async def test_tools_call_full_harness_search_municode_matches_harness_router(client):
    fake_session = FakeSession()
    with patch(
        "plotlot.api.tools.get_session",
        new=AsyncMock(return_value=fake_session),
    ):
        response = await client.post(
            "/api/v1/tools/call",
            json={
                "tool_name": "search_municode",
                "arguments": {"jurisdiction": "miami", "query": "parking"},
                "workspace_id": "ws_test",
                "run_id": "run_test_harness_rest_bridge",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["tool_name"] == "search_municode"
    assert payload["result"]["results"][0]["section_id"] == "municode_miami_parking_fixture"
    assert payload["decision"]["approval_required"] is False
    assert [event["type"] for event in payload["events"]] == [
        "tool.requested",
        "tool.policy_checked",
        "tool.started",
        "tool.completed",
    ]
    assert payload["source_mode"] == "fixture"


@pytest.mark.asyncio
async def test_tools_call_full_harness_success_persists_tool_run(client):
    from plotlot.storage.models import ToolRun

    fake_session = FakeSession()
    with patch("plotlot.api.tools.get_session", new=AsyncMock(return_value=fake_session)):
        response = await client.post(
            "/api/v1/tools/call",
            json={
                "tool_name": "search_municode",
                "arguments": {"jurisdiction": "miami", "query": "parking"},
                "workspace_id": "ws_test",
                "run_id": "run_test_harness_rest_bridge_commit",
                "source_mode": "fixture",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    tool_runs = [obj for obj in fake_session.added if isinstance(obj, ToolRun)]
    assert len(tool_runs) == 1
    assert payload["tool_run_id"] == str(tool_runs[0].id)
    assert tool_runs[0].tool_name == "search_municode"
    assert tool_runs[0].status == "ok"
    assert fake_session.committed is True


@pytest.mark.asyncio
async def test_tools_call_full_harness_export_report_requires_approval(client):
    fake_session = FakeSession()
    with patch(
        "plotlot.api.tools.get_session",
        new=AsyncMock(return_value=fake_session),
    ):
        response = await client.post(
            "/api/v1/tools/call",
            json={
                "tool_name": "export_report",
                "arguments": {"report_id": "report_fixture"},
                "workspace_id": "ws_test",
                "run_id": "run_test_harness_export",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "pending_approval"
    assert payload["tool_name"] == "export_report"
    assert payload["decision"]["approval_required"] is True
    assert [event["type"] for event in payload["events"]] == [
        "tool.requested",
        "tool.policy_checked",
        "tool.approval_required",
    ]
    assert payload["source_mode"] == "fixture"


@pytest.mark.asyncio
async def test_tools_call_full_harness_approval_persists_tool_run_and_approval(client):
    from plotlot.storage.models import ApprovalRequest, ToolRun

    fake_session = FakeSession()
    with patch("plotlot.api.tools.get_session", new=AsyncMock(return_value=fake_session)):
        response = await client.post(
            "/api/v1/tools/call",
            json={
                "tool_name": "export_report",
                "arguments": {"report_id": "report_fixture"},
                "workspace_id": "ws_test",
                "run_id": "run_test_harness_export_commit",
                "source_mode": "fixture",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "pending_approval"
    tool_runs = [obj for obj in fake_session.added if isinstance(obj, ToolRun)]
    approvals = [obj for obj in fake_session.added if isinstance(obj, ApprovalRequest)]
    assert len(tool_runs) == 1
    assert payload["tool_run_id"] == str(tool_runs[0].id)
    assert tool_runs[0].tool_name == "export_report"
    assert tool_runs[0].status == "pending_approval"
    assert len(approvals) == 1
    assert approvals[0].action_name == "export_report"
    assert approvals[0].status == "pending"
    assert fake_session.committed is True


@pytest.mark.asyncio
async def test_tools_call_generate_document_persists_artifacts(client):
    fake_session = FakeSession()
    with patch("plotlot.api.tools.get_session", new=AsyncMock(return_value=fake_session)):
        resp = await client.post(
            "/api/v1/tools/call",
            json={
                "tool_name": "generate_document",
                "arguments": {
                    "title": "Test Report",
                    "evidence_ids": ["ev_1", "ev_2"],
                },
                "workspace_id": "ws_test",
                "run_id": "run_test_3",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending_approval"
    assert data["decision"]["approval_required"] is True
    assert data["decision"]["approval_id"]


@pytest.mark.asyncio
async def test_tools_call_draft_email_is_allowed_and_persists_document_artifact(client):
    fake_session = FakeSession()
    with patch("plotlot.api.tools.get_session", new=AsyncMock(return_value=fake_session)):
        resp = await client.post(
            "/api/v1/tools/call",
            json={
                "tool_name": "draft_email",
                "arguments": {
                    "to": ["owner@example.com"],
                    "subject": "Site feasibility follow-up",
                    "body": "Hi — sharing a draft note for review.",
                    "evidence_ids": ["ev_1"],
                },
                "workspace_id": "ws_test",
                "run_id": "run_test_draft_1",
            },
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["result"]["status"] == "drafted"
    assert "document_id" in data["artifact_ids"]


@pytest.mark.asyncio
async def test_tools_call_gmail_send_draft_requires_approval_before_connector_execution(client):
    from plotlot.storage.models import ApprovalRequest

    fake_session = FakeSession()
    with patch("plotlot.api.tools.get_session", new=AsyncMock(return_value=fake_session)):
        resp = await client.post(
            "/api/v1/tools/call",
            json={
                "tool_name": "gmail_send_draft",
                "arguments": {"draft_id": "draft_email_123"},
                "workspace_id": "ws_test",
                "run_id": "run_test_send_1",
                "live_network_allowed": True,
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending_approval"
    assert data["decision"]["approval_required"] is True
    assert data["decision"]["approval_id"] == "apr_run_test_send_1_gmail_send_draft"

    approvals = [obj for obj in fake_session.added if isinstance(obj, ApprovalRequest)]
    assert len(approvals) == 1
    assert approvals[0].action_name == "gmail_send_draft"
    assert fake_session.committed is True


@pytest.mark.asyncio
async def test_tools_call_web_search_synthesizes_and_persists_evidence(client):
    from unittest.mock import AsyncMock, patch

    from plotlot.harness.web_lookup import WebLookupStatus, WebSearchResult, WebSearchResultItem

    fake_session = FakeSession()
    search_result = WebSearchResult(
        status=WebLookupStatus.SUCCESS,
        results=[
            WebSearchResultItem(
                title="RM-3-7 setbacks",
                url="https://example.com/rm-3-7",
                description="Setback summary",
                content="Front setback 15 feet.",
            )
        ],
    )

    with (
        patch("plotlot.api.tools.get_session", new=AsyncMock(return_value=fake_session)),
        patch(
            "plotlot.harness.tool_router_handlers.execute_web_search",
            new=AsyncMock(return_value=search_result),
        ),
    ):
        resp = await client.post(
            "/api/v1/tools/call",
            json={
                "tool_name": "web_search",
                "arguments": {"query": "RM-3-7 setbacks"},
                "workspace_id": "ws_test",
                "run_id": "run_test_web_search_1",
                "risk_budget_cents": 100,
                "live_network_allowed": True,
            },
        )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["status"] == "ok"
    assert len(payload["evidence_ids"]) == 1
    result_item = payload["result"]["results"][0]
    assert result_item["evidence_id"] == payload["evidence_ids"][0]
    assert result_item["citation"]["url"] == "https://example.com/rm-3-7"
    assert payload["result"]["evidence"][0]["tool_name"] == "web_search"
