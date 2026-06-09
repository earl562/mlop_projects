"""Unit tests for event scoring logic."""
from __future__ import annotations

import pytest
from outreach.tools.eventbrite import _score_event


def test_high_relevance_keywords():
    score = _score_event("ULI Land Acquisition Forum", "land acquisition zoning entitlements homebuilder")
    assert score > 0.5


def test_low_relevance():
    score = _score_event("Tech Startup Pitch Night", "SaaS B2B software venture capital")
    assert score == 0.0


def test_partial_relevance():
    score = _score_event("Real Estate Development Conference", "development finance investing")
    assert 0.0 < score <= 1.0


def test_score_capped_at_one():
    # Throw every keyword at it
    name = " ".join(["land acquisition", "zoning", "entitlements", "homebuilder"])
    desc = " ".join(["real estate development", "ULI", "BIA", "NAIOP", "multifamily"])
    score = _score_event(name, desc)
    assert score <= 1.0


def test_case_insensitive_scoring():
    score1 = _score_event("ULI FORUM", "LAND ACQUISITION ZONING")
    score2 = _score_event("uli forum", "land acquisition zoning")
    assert score1 == score2
