"""Tests for the neighbor/political opposition risk module."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from plotlot.core.types import OppositionRiskAssessment
from plotlot.pipeline.opposition_risk import (
    _density_delta_description,
    _heuristic_risk_level,
    assess_opposition_risk,
)


# ---------------------------------------------------------------------------
# Density delta description
# ---------------------------------------------------------------------------


def test_density_delta_large_project():
    desc, flags = _density_delta_description(50, "RM-3-7", "San Diego")
    assert "50+" in desc or "50" in desc
    assert any("larger project" in f.lower() for f in flags)


def test_density_delta_small_project():
    desc, flags = _density_delta_description(2, "R-1", "Sausalito")
    assert "Low-density" in desc
    assert any("single-family" in f.lower() for f in flags)


def test_density_delta_multifamily_in_sf_zone():
    desc, flags = _density_delta_description(8, "R-1", "Tiburon")
    assert any("single-family" in f.lower() for f in flags)


def test_density_delta_no_max_units():
    desc, flags = _density_delta_description(None, "", "Nowhere")
    assert "not determined" in desc
    assert len(flags) == 0


# ---------------------------------------------------------------------------
# Heuristic risk level
# ---------------------------------------------------------------------------


def test_heuristic_risk_low():
    assert _heuristic_risk_level(2, [], False) == "low"


def test_heuristic_risk_moderate():
    assert _heuristic_risk_level(20, [], False) == "moderate"


def test_heuristic_risk_high_large_project_in_sf_zone():
    # 50 units + SF zone = high
    assert _heuristic_risk_level(50, [], True) == "high"


def test_heuristic_risk_high_sf_zone_with_flags():
    assert _heuristic_risk_level(10, ["Some flag"], True) == "high"


# ---------------------------------------------------------------------------
# Full assessment (mocked LLM + web search)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assess_opposition_risk_basic():
    with (
        patch(
            "plotlot.pipeline.opposition_risk._suggest_possible_controversies",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "plotlot.pipeline.opposition_risk._llm_opposition_assessment",
            new=AsyncMock(return_value="Low density infill — minimal opposition expected."),
        ),
    ):
        result = await assess_opposition_risk(
            address="123 Main St",
            municipality="San Diego",
            county="San Diego",
            state="CA",
            max_units=6,
            zoning_district="RM-3-7",
        )

    assert isinstance(result, OppositionRiskAssessment)
    assert result.risk_level in ("low", "moderate", "high")
    assert result.confidence == "low"
    assert len(result.assessment) > 0
    assert len(result.data_sources) > 0


@pytest.mark.asyncio
async def test_assess_opposition_risk_high_density_sf_zone():
    with (
        patch(
            "plotlot.pipeline.opposition_risk._suggest_possible_controversies",
            new=AsyncMock(return_value=["Neighbors opposed similar project in 2025"]),
        ),
        patch(
            "plotlot.pipeline.opposition_risk._llm_opposition_assessment",
            new=AsyncMock(return_value="High opposition risk due to density change."),
        ),
    ):
        result = await assess_opposition_risk(
            address="456 Oak Ave",
            municipality="Tiburon",
            county="Marin",
            state="CA",
            max_units=24,
            zoning_district="R-1",
        )

    assert result.risk_level == "high"
    assert len(result.flags) >= 1
    assert any("single-family" in f.lower() for f in result.flags)


@pytest.mark.asyncio
async def test_assess_opposition_risk_api_failure_degrades_gracefully():
    with (
        patch(
            "plotlot.pipeline.opposition_risk._suggest_possible_controversies",
            new=AsyncMock(side_effect=Exception("network error")),
        ),
        patch(
            "plotlot.pipeline.opposition_risk._llm_opposition_assessment",
            new=AsyncMock(side_effect=Exception("LLM unavailable")),
        ),
    ):
        result = await assess_opposition_risk(
            address="789 Pine St",
            municipality="Miami",
            county="Miami-Dade",
            state="FL",
            max_units=4,
            zoning_district="R-3",
        )

    # Should still return a heuristic-based assessment
    assert isinstance(result, OppositionRiskAssessment)
    assert result.risk_level is not None
    assert result.confidence == "low"


@pytest.mark.asyncio
async def test_assess_opposition_risk_no_max_units():
    with (
        patch(
            "plotlot.pipeline.opposition_risk._suggest_possible_controversies",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "plotlot.pipeline.opposition_risk._llm_opposition_assessment",
            new=AsyncMock(return_value=""),
        ),
    ):
        result = await assess_opposition_risk(
            address="123 Main St",
            municipality="Unknown",
            county="Unknown",
            state="CA",
            max_units=None,
            zoning_district="",
        )

    assert result.risk_level == "low"
    assert result.confidence == "low"
