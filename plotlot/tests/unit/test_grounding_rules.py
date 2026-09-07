"""Regression tests — grounding rules prevent hallucination across all prompts.

Every test verifies a specific anti-hallucination constraint so future edits
cannot accidentally re-introduce the pattern that caused wrong zoning outputs.
"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Analysis prompt grounding
# ---------------------------------------------------------------------------


def test_analysis_prompt_does_not_reference_south_florida():
    from plotlot.observability.prompts import ANALYSIS_PROMPT_V1

    assert "South Florida" not in ANALYSIS_PROMPT_V1
    assert "south florida" not in ANALYSIS_PROMPT_V1.lower()


def test_analysis_prompt_does_not_allow_filling_gaps_from_knowledge():
    from plotlot.observability.prompts import ANALYSIS_PROMPT_V1

    # These phrases explicitly enabled hallucination — must not reappear
    forbidden = [
        "use your expert knowledge",
        "fill gaps",
        "expert knowledge of",
        "your knowledge",
    ]
    for phrase in forbidden:
        assert phrase.lower() not in ANALYSIS_PROMPT_V1.lower(), (
            f"Hallucination enabler found in analysis prompt: {phrase!r}"
        )


def test_analysis_prompt_requires_null_when_not_found():
    from plotlot.observability.prompts import ANALYSIS_PROMPT_V1

    assert "null" in ANALYSIS_PROMPT_V1.lower()
    assert "not" in ANALYSIS_PROMPT_V1.lower() and "found" in ANALYSIS_PROMPT_V1.lower()


def test_analysis_prompt_requires_4_searches():
    from plotlot.observability.prompts import ANALYSIS_PROMPT_V1

    assert "4" in ANALYSIS_PROMPT_V1


def test_analysis_prompt_has_grounding_verification_rule():
    from plotlot.observability.prompts import ANALYSIS_PROMPT_V1

    assert "grounding" in ANALYSIS_PROMPT_V1.lower() or "verify" in ANALYSIS_PROMPT_V1.lower()


# ---------------------------------------------------------------------------
# Direct system prompt (llm.py) grounding
# ---------------------------------------------------------------------------


def test_direct_prompt_does_not_reference_south_florida():
    from plotlot.retrieval.llm import DIRECT_SYSTEM_PROMPT

    assert "South Florida" not in DIRECT_SYSTEM_PROMPT
    assert "south florida" not in DIRECT_SYSTEM_PROMPT.lower()


def test_direct_prompt_has_grounding_rule():
    from plotlot.retrieval.llm import DIRECT_SYSTEM_PROMPT

    assert (
        "grounding" in DIRECT_SYSTEM_PROMPT.lower() or "not found" in DIRECT_SYSTEM_PROMPT.lower()
    )
    assert (
        "training knowledge" in DIRECT_SYSTEM_PROMPT.lower()
        or "empty string" in DIRECT_SYSTEM_PROMPT.lower()
    )


# ---------------------------------------------------------------------------
# lookup.py re-prompt grounding
# ---------------------------------------------------------------------------


def test_lookup_reprompt_does_not_use_expert_knowledge():
    import inspect
    from plotlot.pipeline import lookup

    source = inspect.getsource(lookup)
    assert "use your expert knowledge" not in source
    assert "expert knowledge and set confidence" not in source


def test_lookup_max_turns_allows_enough_searches():
    from plotlot.pipeline.lookup import MAX_ANALYSIS_TURNS

    # Must be at least 6 to allow 4 searches + submit + possible retry
    assert MAX_ANALYSIS_TURNS >= 6, (
        f"MAX_ANALYSIS_TURNS={MAX_ANALYSIS_TURNS} is too low — "
        "need at least 6 to fit 4 targeted searches before submit_report"
    )


# ---------------------------------------------------------------------------
# Chat agent prompt grounding
# ---------------------------------------------------------------------------


def test_chat_prompt_has_grounding_rule():
    from plotlot.observability.prompts import get_active_prompt

    prompt = get_active_prompt("chat_agent")
    assert "grounding" in prompt.lower() or "hallucin" in prompt.lower()
    assert "training knowledge" in prompt.lower()


def test_chat_prompt_requires_section_citation():
    from plotlot.observability.prompts import get_active_prompt

    prompt = get_active_prompt("chat_agent")
    assert "section" in prompt.lower() or "cite" in prompt.lower()


def test_chat_prompt_version_is_v7():
    from plotlot.observability.prompts import get_prompt_version

    assert get_prompt_version("chat_agent") == "v7"


def test_chat_prompt_forbids_fabricating_contacts_and_urls():
    """Regression: agent fabricated a Clark County phone number for un-indexed RS20."""
    from plotlot.observability.prompts import get_active_prompt

    prompt = get_active_prompt("chat_agent").lower()
    assert "phone number" in prompt
    assert "url" in prompt
    # Must forbid invention of contacts/links
    assert "never invent" in prompt or "never fabricate" in prompt


def test_chat_prompt_forbids_zoning_not_retrieved_when_code_known():
    """When a zoning_code is known, the agent must not claim zoning was unavailable."""
    from plotlot.observability.prompts import get_active_prompt

    prompt = get_active_prompt("chat_agent").lower()
    assert "could not be retrieved" in prompt  # the forbidden phrasing is named
    assert "not yet in the plotlot database" in prompt  # the honest alternative
    assert "ingest" in prompt  # offers the remedy
