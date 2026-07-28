"""Unit tests for MCP HTTP endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from plotlot.api.auth_types import Actor, IdentityRole, capabilities_for_role


@pytest.fixture(autouse=True)
def _verified_mcp_actor():
    role = IdentityRole.OWNER
    actor = Actor(
        user_id="mcp-test-owner",
        tenant_id="ws_test",
        role=role,
        capabilities=capabilities_for_role(role),
    )
    with patch(
        "plotlot.api.security_middleware.get_current_user",
        new=AsyncMock(return_value=actor.as_request_user()),
    ):
        yield


class FakeSession:
    def __init__(self):
        self.added = []
        self.committed = False
        self.rolled_back = False

    async def get(self, model, key):  # noqa: ANN001
        return None

    def add(self, obj):  # noqa: ANN001
        self.added.append(obj)

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

    async def close(self):
        return None


@pytest.mark.asyncio
async def test_mcp_tools_list_includes_core_tools(client):
    resp = await client.get("/api/v1/mcp/tools/list")
    assert resp.status_code == 200
    data = resp.json()
    names = {t["name"] for t in data}
    assert "geocode_address" in names
    assert "discover_open_data_layers" in names
    assert "discover_municode_authorities" in names
    assert "discover_code_authorities" in names
    assert "search_code_authority_live" in names
    assert "draft_email" in names
    assert "create_spreadsheet" in names
    assert "gmail_send_draft" in names


@pytest.mark.asyncio
async def test_mcp_tools_call_geocode(client):
    async def _fake_geocode(address: str):
        return {
            "formatted_address": address,
            "municipality": "Example",
            "county": "Example",
            "state": "FL",
            "lat": 1.23,
            "lng": 4.56,
        }

    with patch("plotlot.retrieval.geocode.geocode_address", new=_fake_geocode):
        resp = await client.post(
            "/api/v1/mcp/tools/call",
            json={
                "name": "geocode_address",
                "arguments": {"address": "123 Main St"},
                "context": {
                    "workspace_id": "ws_test",
                    "run_id": "run_mcp_1",
                    "project_id": "prj_test",
                    "approved_approval_ids": [],
                },
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["result"]["status"] == "success"
    assert data["result"]["result"]["municipality"] == "Example"


@pytest.mark.asyncio
async def test_mcp_lookup_property_info_passes_state_to_dynamic_lookup(client):
    from plotlot.core.types import PropertyRecord

    calls = []

    async def _fake_lookup_property(address, county, lat=None, lng=None, state=""):  # noqa: ANN001
        calls.append(
            {
                "address": address,
                "county": county,
                "lat": lat,
                "lng": lng,
                "state": state,
            }
        )
        return PropertyRecord(
            folio="1703-01-2345",
            address=address,
            municipality="Raleigh",
            county=county,
            owner="Wake County",
            zoning_code="DX-3",
            lot_size_sqft=10000,
            lat=lat,
            lng=lng,
        )

    with patch("plotlot.retrieval.property.lookup_property", new=_fake_lookup_property):
        resp = await client.post(
            "/api/v1/mcp/tools/call",
            json={
                "name": "lookup_property_info",
                "arguments": {
                    "address": "222 W Hargett St, Raleigh, NC",
                    "county": "Wake",
                    "state": "NC",
                    "lat": 35.7789,
                    "lng": -78.6418,
                },
                "context": {
                    "workspace_id": "ws_test",
                    "run_id": "run_mcp_wake_lookup",
                    "project_id": "prj_test",
                    "approved_approval_ids": [],
                },
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["result"]["status"] == "success"
    assert data["result"]["result"]["county"] == "Wake"
    assert calls == [
        {
            "address": "222 W Hargett St, Raleigh, NC",
            "county": "Wake",
            "lat": 35.7789,
            "lng": -78.6418,
            "state": "NC",
        }
    ]


@pytest.mark.asyncio
async def test_mcp_search_properties_accepts_dynamic_county_state(client):
    searched = []

    async def _fake_bulk_property_search(params):  # noqa: ANN001
        searched.append(params)
        return [
            {
                "folio": "1703-01-2345",
                "address": "222 W HARGETT ST",
                "city": "RALEIGH",
                "county": "Wake",
                "owner": "WAKE COUNTY",
                "land_use_code": "",
                "lot_size_sqft": 21780.0,
                "year_built": 0,
                "assessed_value": 125000.0,
                "last_sale_price": 0.0,
                "last_sale_date": "",
                "lat": 35.7789,
                "lng": -78.6418,
            }
        ]

    with patch(
        "plotlot.retrieval.bulk_search.bulk_property_search", new=_fake_bulk_property_search
    ):
        resp = await client.post(
            "/api/v1/mcp/tools/call",
            json={
                "name": "search_properties",
                "arguments": {
                    "county": "Wake",
                    "state": "NC",
                    "lat": 35.7789,
                    "lng": -78.6418,
                    "city": "Raleigh",
                    "max_results": 5,
                },
                "context": {
                    "workspace_id": "ws_test",
                    "run_id": "run_mcp_wake_search",
                    "project_id": "prj_test",
                    "approved_approval_ids": [],
                },
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["result"]["status"] == "success"
    assert data["result"]["total_results"] == 1
    assert searched[0].county == "Wake"
    assert searched[0].state == "NC"
    assert searched[0].lat == 35.7789
    assert searched[0].lng == -78.6418


@pytest.mark.asyncio
async def test_mcp_discover_municode_authorities_returns_county_matches(client):
    from plotlot.core.types import MunicodeConfig

    async def _fake_get_municode_configs(force_refresh=False):  # noqa: ARG001
        return {
            "wake_county": MunicodeConfig(
                municipality="Wake County",
                county="wake",
                client_id=10,
                product_id=20,
                job_id=30,
                zoning_node_id="WAKE_ZONING",
                state="NC",
            ),
            "ca_wake_county": MunicodeConfig(
                municipality="Wake County",
                county="wake",
                client_id=40,
                product_id=50,
                job_id=60,
                zoning_node_id="CA_WAKE_ZONING",
                state="CA",
            ),
        }

    with patch("plotlot.ingestion.discovery.get_municode_configs", new=_fake_get_municode_configs):
        resp = await client.post(
            "/api/v1/mcp/tools/call",
            json={
                "name": "discover_municode_authorities",
                "arguments": {"county": "Wake", "state": "NC"},
                "context": {
                    "workspace_id": "ws_test",
                    "run_id": "run_mcp_wake_municode",
                    "project_id": "prj_test",
                    "approved_approval_ids": [],
                },
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["result"]["status"] == "success"
    assert data["result"]["results"] == [
        {
            "municipality": "Wake County",
            "county": "wake",
            "state": "NC",
            "client_id": 10,
            "product_id": 20,
            "job_id": 30,
            "zoning_node_id": "WAKE_ZONING",
        }
    ]


@pytest.mark.asyncio
async def test_mcp_discover_code_authorities_returns_non_municode_sources(client):
    from plotlot.land_use.code_providers import CodeAuthority

    async def _fake_discover_code_authorities(*, county, state, include_web_fallback=True):  # noqa: ANN001
        assert county == "Alpine"
        assert state == "CA"
        assert include_web_fallback is True
        return [
            CodeAuthority(
                county="Alpine",
                state="CA",
                name="Alpine County, CA",
                authority_type="county",
                platform="codepublishing",
                publisher="Code Publishing",
                source_url="https://www.codepublishing.com/CA/AlpineCounty/",
                status="available",
                jurisdiction_id="ca-alpine-county",
                discovery_source="openlegalcodes",
                confidence="high",
            )
        ]

    with patch(
        "plotlot.land_use.code_providers.discover_code_authorities",
        new=_fake_discover_code_authorities,
    ):
        resp = await client.post(
            "/api/v1/mcp/tools/call",
            json={
                "name": "discover_code_authorities",
                "arguments": {"county": "Alpine", "state": "CA"},
                "context": {
                    "workspace_id": "ws_test",
                    "run_id": "run_mcp_alpine_code",
                    "project_id": "prj_test",
                    "approved_approval_ids": [],
                },
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["result"]["status"] == "success"
    assert data["result"]["results"][0]["platform"] == "codepublishing"
    assert data["result"]["results"][0]["jurisdiction_id"] == "ca-alpine-county"


@pytest.mark.asyncio
async def test_mcp_search_code_authority_live_handles_pending_source(client):
    async def _fake_search_openlegalcodes(*, jurisdiction_id, query, limit=5):  # noqa: ANN001
        assert jurisdiction_id == "ca-alpine-county"
        assert query == "setback"
        return {
            "status": "pending_or_unavailable",
            "results": [],
            "message": "Data is being fetched.",
            "retry_after": 30,
        }

    with patch(
        "plotlot.land_use.code_providers.search_openlegalcodes",
        new=_fake_search_openlegalcodes,
    ):
        resp = await client.post(
            "/api/v1/mcp/tools/call",
            json={
                "name": "search_code_authority_live",
                "arguments": {
                    "jurisdiction_id": "ca-alpine-county",
                    "query": "setback",
                    "limit": 3,
                },
                "context": {
                    "workspace_id": "ws_test",
                    "run_id": "run_mcp_alpine_code_search",
                    "project_id": "prj_test",
                    "approved_approval_ids": [],
                },
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["result"]["status"] == "pending_or_unavailable"
    assert data["result"]["retry_after"] == 30


@pytest.mark.asyncio
async def test_mcp_tools_call_write_external_requires_approval_and_persists_request(client):
    from unittest.mock import AsyncMock

    from plotlot.storage.models import ApprovalRequest

    fake_session = FakeSession()

    with patch("plotlot.api.mcp.get_session", new=AsyncMock(return_value=fake_session)):
        resp = await client.post(
            "/api/v1/mcp/tools/call",
            json={
                "name": "gmail_send_draft",
                "arguments": {"draft_id": "draft_email_123"},
                "context": {
                    "workspace_id": "ws_test",
                    "run_id": "run_mcp_send_1",
                    "project_id": "prj_test",
                    "approved_approval_ids": [],
                },
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "pending_approval"
    assert data["decision"]["approval_required"] is True

    approvals = [obj for obj in fake_session.added if isinstance(obj, ApprovalRequest)]
    assert len(approvals) == 1
    assert fake_session.committed is True
