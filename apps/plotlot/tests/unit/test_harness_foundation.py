"""Tests for the workspace harness foundation."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from httpx import ASGITransport, AsyncClient

from plotlot.api.main import app
from plotlot.core.types import Setbacks, ZoningReport
from plotlot.harness import GovernanceMiddleware, SkillInput, SkillRegistry
from plotlot.harness.bootstrap import build_default_runtime
from plotlot.harness.contracts import SkillOutput
from plotlot.storage.db import get_session


class _DummySkill:
    name = "dummy"
    triggers = ("dummy",)

    async def run(self, runtime, skill_input: SkillInput) -> SkillOutput:
        _ = runtime
        return SkillOutput(status="success", summary=skill_input.prompt)


@pytest.mark.asyncio
async def test_harness_runtime_routes_to_registered_skill():
    registry = SkillRegistry()
    registry.register(_DummySkill())
    runtime = build_default_runtime()
    runtime.registry = registry

    output = await runtime.run(SkillInput(prompt="please run dummy workflow"))

    assert output.status == "success"
    assert output.summary == "please run dummy workflow"


def test_governance_blocks_external_writes_by_default(monkeypatch):
    from plotlot.config import settings

    monkeypatch.setattr(settings, "tool_permission_mode", "read_only")
    decision = GovernanceMiddleware().decide("create_document")

    assert not decision.allowed
    assert decision.status.value == "blocked"
    assert "read_only" in decision.reason


@pytest.mark.asyncio
async def test_zoning_research_skill_wraps_lookup_pipeline(monkeypatch):
    report = ZoningReport(
        address="123 Main St",
        formatted_address="123 Main St, Miami, FL",
        municipality="Miami",
        county="Miami-Dade",
        zoning_district="RU-1",
        allowed_uses=["single-family"],
        setbacks=Setbacks(front="25 ft", side="7.5 ft", rear="25 ft"),
        summary="Single-family zoning report.",
        sources=["Sec. 33-1"],
        confidence="high",
    )
    monkeypatch.setattr(
        "plotlot.skills.zoning_research.workflow.lookup_address",
        AsyncMock(return_value=report),
    )

    runtime = build_default_runtime()
    output = await runtime.run(
        SkillInput(
            prompt="What can I build?",
            payload={"address": "123 Main St"},
        ),
        skill_name="zoning_research",
    )

    assert output.status == "success"
    assert output.data["report"]["zoning_district"] == "RU-1"
    assert output.data["evidence_candidates"][0]["source_title"] == "Sec. 33-1"


@pytest.mark.asyncio
async def test_ordinance_search_endpoint_wraps_hybrid_search(monkeypatch):
    from plotlot.core.types import SearchResult

    async def fake_get_session():
        yield object()

    app.dependency_overrides[get_session] = fake_get_session
    monkeypatch.setattr(
        "plotlot.api.ordinances.hybrid_search",
        AsyncMock(
            return_value=[
                SearchResult(
                    section="33-1",
                    section_title="RU-1 District",
                    zone_codes=["RU-1"],
                    chunk_text="Minimum front setback is 25 feet.",
                    municipality="Miami-Dade",
                    score=0.91,
                )
            ]
        ),
    )
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/ordinances/search",
                json={"municipality": "Miami-Dade", "query": "RU-1 setback", "limit": 3},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    data = response.json()
    assert data["results"][0]["section"] == "33-1"
    assert "25 feet" in data["results"][0]["text_preview"]
