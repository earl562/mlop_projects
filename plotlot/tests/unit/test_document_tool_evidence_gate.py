from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from plotlot.storage.models import Document, EvidenceItem, Project, Report, Workspace

_AddedRow = Document | Project | Report | Workspace
_LookupModel = type[Document] | type[EvidenceItem] | type[Project] | type[Report] | type[Workspace]


class FakeSession:
    def __init__(self, *, recorded_evidence_ids: set[str] | None = None) -> None:
        self.added: list[_AddedRow] = []
        self.committed = False
        self.rolled_back = False
        self.recorded_evidence_ids = recorded_evidence_ids or set()

    async def get(self, model: _LookupModel, key: str) -> SimpleNamespace | None:
        if model.__name__ == "EvidenceItem" and key in self.recorded_evidence_ids:
            return SimpleNamespace(id=key)
        return None

    def add(self, obj: _AddedRow) -> None:
        self.added.append(obj)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_generate_document_blocks_unsupported_material_claims_across_adapters(client):
    from plotlot.harness.default_runtime import get_default_runtime
    from plotlot.harness.mcp_adapter import MCPAdapter
    from plotlot.land_use.models import ToolContext

    arguments = {
        "title": "Investor Memo",
        "sections": [
            {
                "id": "zoning",
                "title": "Zoning",
                "claims": [
                    {
                        "key": "zoning.max_units",
                        "text": "The site supports 12 units by right.",
                        "material": True,
                    }
                ],
            }
        ],
        "assumptions": [
            {
                "key": "rent.market",
                "text": "Market rent assumed at $2,400 per unit.",
            }
        ],
    }

    fake_session = FakeSession()
    with patch("plotlot.api.tools.get_session", new=AsyncMock(return_value=fake_session)):
        resp = await client.post(
            "/api/v1/tools/call",
            json={
                "tool_name": "generate_document",
                "arguments": arguments,
                "workspace_id": "ws_test",
                "run_id": "run_test_document_claim_gate",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "blocked"
    assert data["result"]["status"] == "blocked"
    assert data["result"]["unsupported_claim_keys"] == ["zoning.max_units"]
    assert data["result"]["assumption_keys"] == ["rent.market"]
    assert data["artifact_ids"] == {}

    adapter = MCPAdapter(get_default_runtime())
    mcp_result = await adapter.call_tool(
        name="generate_document",
        arguments=arguments,
        context=ToolContext(
            workspace_id="ws_test",
            actor_user_id="anonymous",
            run_id="run_test_document_claim_gate_mcp",
            project_id="prj_test",
            risk_budget_cents=0,
        ),
    )

    assert mcp_result.status == "blocked"
    assert mcp_result.result is not None
    assert mcp_result.result["unsupported_claim_keys"] == ["zoning.max_units"]


@pytest.mark.asyncio
async def test_generate_document_persists_evidence_backed_sections_and_assumptions(client):
    arguments = {
        "title": "Evidence Memo",
        "evidence_ids": ["ev_code"],
        "sections": [
            {
                "id": "zoning",
                "title": "Zoning",
                "evidence_ids": ["ev_code"],
                "claims": [
                    {
                        "key": "zoning.max_units",
                        "text": "The verified ordinance evidence supports the stated unit cap.",
                        "material": True,
                        "evidence_ids": ["ev_code"],
                    }
                ],
            }
        ],
        "assumptions": [
            {
                "key": "rent.market",
                "text": "Market rent assumed at $2,400 per unit.",
            }
        ],
    }

    fake_session = FakeSession(recorded_evidence_ids={"ev_code"})
    with patch("plotlot.api.tools.get_session", new=AsyncMock(return_value=fake_session)):
        resp = await client.post(
            "/api/v1/tools/call",
            json={
                "tool_name": "generate_document",
                "arguments": arguments,
                "workspace_id": "ws_test",
                "run_id": "run_test_document_evidence_gate",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "report_id" in data["artifact_ids"]

    reports = [obj for obj in fake_session.added if isinstance(obj, Report)]
    assert len(reports) == 1
    report_json = reports[0].report_json
    assert report_json["evidence_ids"] == ["ev_code"]
    assert report_json["sections"][0]["claims"][0]["evidence_ids"] == ["ev_code"]
    assert report_json["assumptions"] == [
        {
            "key": "rent.market",
            "text": "Market rent assumed at $2,400 per unit.",
        }
    ]


@pytest.mark.asyncio
async def test_mcp_generate_document_persists_artifacts_with_recorded_evidence(client):
    arguments = {
        "title": "MCP Evidence Memo",
        "evidence_ids": ["ev_mcp_code"],
        "sections": [
            {
                "id": "zoning",
                "title": "Zoning",
                "claims": [
                    {
                        "key": "zoning.allowed_uses",
                        "text": "The verified ordinance evidence supports the stated use.",
                        "material": True,
                        "evidence_ids": ["ev_mcp_code"],
                    }
                ],
            }
        ],
        "assumptions": [
            {
                "key": "rent.market",
                "text": "Market rent remains an underwriting assumption.",
            }
        ],
    }

    fake_session = FakeSession(recorded_evidence_ids={"ev_mcp_code"})
    with patch("plotlot.api.mcp.get_session", new=AsyncMock(return_value=fake_session)):
        resp = await client.post(
            "/api/v1/mcp/tools/call",
            json={
                "name": "generate_document",
                "arguments": arguments,
                "context": {
                    "workspace_id": "ws_mcp_document",
                    "actor_user_id": "anonymous",
                    "run_id": "run_mcp_document_evidence_gate",
                    "project_id": "project_mcp_document",
                    "risk_budget_cents": 0,
                    "live_network_allowed": False,
                    "approved_approval_ids": [],
                },
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["evidence_ids"] == ["ev_mcp_code"]
    assert set(data["artifact_ids"]) == {"report_id", "document_id"}
    assert data["events"][0]["kind"] == "tool_call"
    assert data["events"][-1]["kind"] == "tool_result"

    reports = [obj for obj in fake_session.added if isinstance(obj, Report)]
    documents = [obj for obj in fake_session.added if isinstance(obj, Document)]
    assert len(reports) == 1
    assert len(documents) == 1
    assert reports[0].report_json["evidence_ids"] == ["ev_mcp_code"]
    assert documents[0].metadata_json["evidence_ids"] == ["ev_mcp_code"]
    assert documents[0].metadata_json["assumption_keys"] == ["rent.market"]


@pytest.mark.asyncio
async def test_generate_document_blocks_when_evidence_ids_are_not_recorded(client):
    arguments = {
        "title": "Evidence Memo",
        "evidence_ids": ["ev_missing"],
        "sections": [
            {
                "id": "zoning",
                "title": "Zoning",
                "claims": [
                    {
                        "key": "zoning.max_units",
                        "text": "The verified ordinance evidence supports the stated unit cap.",
                        "material": True,
                        "evidence_ids": ["ev_missing"],
                    }
                ],
            }
        ],
    }

    fake_session = FakeSession()
    with patch("plotlot.api.tools.get_session", new=AsyncMock(return_value=fake_session)):
        resp = await client.post(
            "/api/v1/tools/call",
            json={
                "tool_name": "generate_document",
                "arguments": arguments,
                "workspace_id": "ws_test",
                "run_id": "run_test_missing_recorded_evidence",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "blocked"
    assert data["result"]["status"] == "blocked"
    assert data["result"]["missing_evidence_ids"] == ["ev_missing"]
    assert data["artifact_ids"] == {}
    assert [obj for obj in fake_session.added if isinstance(obj, Report)] == []
