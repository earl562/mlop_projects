"""Unit tests for hybrid search — zone_code_boost and signature regression."""

from __future__ import annotations

import inspect
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from plotlot.retrieval.search import _hybrid_rrf, _keyword_only, hybrid_search


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

    with (
        patch("plotlot.retrieval.search._hybrid_rrf", new=AsyncMock(return_value=[])) as mock_rrf,
        patch("plotlot.retrieval.search.embed_texts", new=AsyncMock(return_value=[[0.1] * 5])),
    ):
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


@pytest.mark.asyncio
async def test_hybrid_rrf_municipality_match_is_bidirectional():
    """Regression: the parcel layer returns composite CDP names ("Belvedere
    Tiburon") while ordinances are ingested under the city ("Tiburon"). The
    municipality filter must match in BOTH directions so the requested name can
    contain the stored key, not only the reverse."""
    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    await _hybrid_rrf(
        session=mock_session,
        municipality="Belvedere Tiburon",
        zone_code="density",
        embedding=[0.0] * 5,
        limit=10,
        zone_code_boost=None,
    )

    clause, params = mock_session.execute.call_args[0][0], mock_session.execute.call_args[0][1]
    sql = str(clause)
    # Reverse-direction predicate present (requested name LIKE %stored_key%)
    assert ":municipality_raw ILIKE" in sql
    # Raw (unwrapped) municipality is passed for the reverse match
    assert params["municipality_raw"] == "Belvedere Tiburon"
    # Forward direction still present (stored key LIKE %requested%)
    assert params["municipality"] == "%Belvedere Tiburon%"


@pytest.mark.asyncio
async def test_keyword_only_municipality_match_is_bidirectional():
    """The keyword-only fallback path must use the same bidirectional match."""
    mock_session = MagicMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    await _keyword_only(
        session=mock_session,
        municipality="Belvedere Tiburon",
        zone_code="density",
        limit=10,
    )

    clause, params = mock_session.execute.call_args[0][0], mock_session.execute.call_args[0][1]
    assert ":municipality_raw ILIKE" in str(clause)
    assert params["municipality_raw"] == "Belvedere Tiburon"
    assert params["municipality"] == "%Belvedere Tiburon%"


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

    assert get_prompt_version("chat_agent") == "v7"


def test_chat_agent_prompt_contains_generate_document_instruction():
    """System prompt must tell agent to call generate_document without passing evidence_ids."""
    from plotlot.observability.prompts import get_active_prompt

    prompt = get_active_prompt("chat_agent")
    assert "generate_document" in prompt
    assert "evidence_ids" in prompt


def test_chat_agent_prompt_contains_session_property_context_rule():
    """Session property context section must exist to prevent lot-size drift."""
    from plotlot.observability.prompts import get_active_prompt

    prompt = get_active_prompt("chat_agent")
    assert "lot_size_sqft" in prompt
    assert "lookup_property_info" in prompt.lower() or "lookup_property" in prompt.lower()


def test_chat_agent_prompt_contains_disambiguation_rule():
    """Disambiguation rule must tell agent to ask before guessing on ambiguous intent."""
    from plotlot.observability.prompts import get_active_prompt

    prompt = get_active_prompt("chat_agent")
    assert "DO NOT guess" in prompt or "Don't guess" in prompt or "don't guess" in prompt.lower()
    assert "clarif" in prompt.lower()


def test_chat_agent_prompt_does_not_hardcode_whole_area():
    """The fix must be generic — must not hardcode the phrase 'whole area' as a rule."""
    from plotlot.observability.prompts import get_active_prompt

    prompt = get_active_prompt("chat_agent")
    # 'whole area' may appear as an example in context, but the rule itself
    # must cover ambiguous intent generically, not just this one phrase
    assert "ambiguous" in prompt.lower() or "unclear" in prompt.lower()
