"""Unit tests for hybrid search — zone_code_boost and signature regression."""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from plotlot.retrieval.search import _hybrid_rrf, hybrid_search


def test_hybrid_search_accepts_zone_code_boost_param():
    sig = inspect.signature(hybrid_search)
    assert "zone_code_boost" in sig.parameters
    assert sig.parameters["zone_code_boost"].default is None


def test_hybrid_rrf_accepts_zone_code_boost_param():
    sig = inspect.signature(_hybrid_rrf)
    assert "zone_code_boost" in sig.parameters
    assert sig.parameters["zone_code_boost"].default is None


@pytest.mark.asyncio
async def test_hybrid_rrf_includes_boost_param_when_provided():
    """When zone_code_boost is given, :zone_code_boost must appear in the SQL params."""
    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    await _hybrid_rrf(
        session=mock_session,
        municipality="San Diego",
        zone_code="RM-3-7 density",
        embedding=[0.0] * 5,
        limit=10,
        zone_code_boost="RM-3-7",
    )

    assert mock_session.execute.called
    call_args = mock_session.execute.call_args
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("parameters", {})
    assert "zone_code_boost" in params
    assert params["zone_code_boost"] == "RM-3-7"


@pytest.mark.asyncio
async def test_hybrid_rrf_omits_boost_param_when_not_provided():
    """When zone_code_boost is None, :zone_code_boost must NOT appear in params (avoids SQL error)."""
    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    await _hybrid_rrf(
        session=mock_session,
        municipality="Oakland",
        zone_code="density",
        embedding=[0.0] * 5,
        limit=10,
        zone_code_boost=None,
    )

    assert mock_session.execute.called
    call_args = mock_session.execute.call_args
    params = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("parameters", {})
    assert "zone_code_boost" not in params


@pytest.mark.asyncio
async def test_hybrid_search_passes_boost_through_to_rrf():
    """hybrid_search must forward zone_code_boost to _hybrid_rrf."""
    mock_session = MagicMock()

    with patch("plotlot.retrieval.search._hybrid_rrf", new=AsyncMock(return_value=[])) as mock_rrf, \
         patch("plotlot.retrieval.search.embed_texts", new=AsyncMock(return_value=[[0.1] * 5])):

        await hybrid_search(
            mock_session,
            "San Diego",
            "RM-3-7 density",
            limit=10,
            zone_code_boost="RM-3-7",
        )

    mock_rrf.assert_called_once()
    _, kwargs = mock_rrf.call_args
    assert kwargs.get("zone_code_boost") == "RM-3-7" or mock_rrf.call_args[0][-1] == "RM-3-7"


def test_chat_agent_prompt_contains_zone_code_prefix_instruction():
    """System prompt must instruct agent to prefix queries with zone code."""
    from plotlot.observability.prompts import get_active_prompt
    prompt = get_active_prompt("chat_agent")
    assert "prefix" in prompt.lower() or "zone code" in prompt.lower()
    assert "RM-3-7" in prompt


def test_chat_agent_prompt_contains_permitted_uses_diversification():
    """System prompt must instruct agent to use distinct queries for use type questions."""
    from plotlot.observability.prompts import get_active_prompt
    prompt = get_active_prompt("chat_agent")
    assert "permitted uses" in prompt.lower()
    assert "conditional uses" in prompt.lower()


def test_chat_agent_prompt_version_updated():
    from plotlot.observability.prompts import get_prompt_version
    assert get_prompt_version("chat_agent") == "v3"
