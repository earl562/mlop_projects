"""Tests for the harness runtime boundary."""

from unittest.mock import AsyncMock, patch

import pytest

from plotlot.harness import HarnessRuntime
from plotlot.harness.default_runtime import _is_pdf_scraped, _handle_search_municode_live
from plotlot.land_use import ToolContext


@pytest.mark.asyncio
async def test_harness_runtime_blocks_external_write_without_approval():
    async def handler(args, context):
        return {"ok": True}

    runtime = HarnessRuntime(handlers={"create_spreadsheet": handler})
    context = ToolContext(
        workspace_id="ws_1",
        actor_user_id="user_1",
        run_id="run_1",
        risk_budget_cents=0,
        live_network_allowed=True,
        approved_approval_ids=set(),
    )

    result = await runtime.call_tool(
        tool_name="create_spreadsheet",
        tool_args={"title": "t", "headers": [], "rows": []},
        context=context,
    )

    assert result.status == "pending_approval"
    assert result.decision.approval_required is True
    assert result.decision.approval_id is not None


@pytest.mark.asyncio
async def test_harness_runtime_calls_handler_when_allowed():
    async def handler(args, context):
        return {"ok": True, "args": args, "workspace_id": context.workspace_id}

    runtime = HarnessRuntime(handlers={"geocode_address": handler})
    context = ToolContext(
        workspace_id="ws_1",
        actor_user_id="user_1",
        run_id="run_1",
        risk_budget_cents=0,
        approved_approval_ids=set(),
    )

    result = await runtime.call_tool(
        tool_name="geocode_address", tool_args={"address": "x"}, context=context
    )

    assert result.status == "ok"
    assert result.result is not None
    assert result.result["workspace_id"] == "ws_1"


# ---------------------------------------------------------------------------
# Bug 2 — search_municode_live serves indexed content for non-Municode cities
# (San Diego is PDF-sourced; its ordinance is in the local index, not Municode).
# ---------------------------------------------------------------------------


def test_is_pdf_scraped_san_diego():
    assert _is_pdf_scraped("San Diego") is True
    assert _is_pdf_scraped("san diego") is True
    assert _is_pdf_scraped("  San Diego  ") is True


def test_is_pdf_scraped_other_cities():
    assert _is_pdf_scraped("Oakland") is False
    assert _is_pdf_scraped("Fort Lauderdale") is False
    assert _is_pdf_scraped("Miami") is False


def _ctx() -> ToolContext:
    return ToolContext(
        workspace_id="ws_test",
        actor_user_id="user_test",
        run_id="run_test",
        risk_budget_cents=0,
        approved_approval_ids=set(),
    )


@pytest.mark.asyncio
async def test_search_municode_live_returns_indexed_content_for_san_diego():
    """San Diego isn't on Municode — the live tool must serve REAL indexed ordinance
    content in one call (delegating to the indexed search), not a dead-end redirect."""
    fake_indexed = {
        "status": "success",
        "results": [
            {"section": "131.0102", "title": "RM-3-7", "snippet": "...", "evidence_id": "ev1"}
        ],
        "evidence": [{"id": "ev1"}],
    }
    with patch(
        "plotlot.harness.default_runtime._handle_search_ordinances",
        new=AsyncMock(return_value=fake_indexed),
    ) as mock_indexed:
        result = await _handle_search_municode_live(
            {"municipality": "San Diego", "query": "RM-3-7 density", "state": "CA"},
            _ctx(),
        )

    mock_indexed.assert_awaited_once()
    assert result["status"] == "success"
    assert result["results"]
    assert result["source"] == "indexed"
    assert "indexed" in result["message"].lower()


@pytest.mark.asyncio
async def test_search_municode_live_san_diego_degrades_honestly_when_unindexed():
    """If San Diego has no indexed text yet, return honest no_results — never fabricate."""
    empty_indexed = {"status": "success", "results": [], "evidence": []}
    with patch(
        "plotlot.harness.default_runtime._handle_search_ordinances",
        new=AsyncMock(return_value=empty_indexed),
    ):
        result = await _handle_search_municode_live(
            {"municipality": "san diego", "query": "setbacks", "state": "CA"},
            _ctx(),
        )

    assert result["status"] == "no_results"
    assert result["results"] == []
    assert "search_zoning_ordinance" in result["message"]
    assert "fabricate" in result["message"].lower()
