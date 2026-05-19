"""Unit tests for Phase 6 — Data Center Site Selection pipeline.

Covers:
- compute_composite_score: weighting, hard disqualifier
- score_zoning_signal: as-of-right / CUP / not-permitted / unknown
- _FLOOD_ZONE_SCORES / _SEISMIC_SCORES: boundary values
- Zoning disqualifier propagates to composite rating
- SiteScorecard fields populated by run_datacenter_pipeline (mocked I/O)
"""

from unittest.mock import AsyncMock, patch

import pytest

from plotlot.core.types import DataCenterParams, InfraSignal, PropertyRecord, SiteScorecard
from plotlot.pipeline.datacenter import (
    _FLOOD_ZONE_SCORES,
    _SEISMIC_SCORES,
    compute_composite_score,
    score_zoning_signal,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _signal(name: str, score: float, confidence: str = "high") -> InfraSignal:
    return InfraSignal(
        name=name,
        label=name,
        score=score,
        rating="Good",
        summary="test",
        raw_value="test",
        source="test",
        confidence=confidence,
    )


def _dc_params(
    permitted: bool | None = True,
    cup: bool | None = False,
    noise: float | None = None,
) -> DataCenterParams:
    return DataCenterParams(
        zoning_code="I-1",
        is_industrial_permitted=permitted,
        conditional_use_required=cup,
        noise_limit_db=noise,
    )


# ---------------------------------------------------------------------------
# score_zoning_signal
# ---------------------------------------------------------------------------


class TestScoreZoningSignal:
    def test_permitted_as_of_right_score_1(self):
        sig = score_zoning_signal(_dc_params(permitted=True, cup=False), "I-1")
        assert sig.score == 1.0
        assert sig.rating == "Excellent"

    def test_cup_required_score_between_0_and_1(self):
        sig = score_zoning_signal(_dc_params(permitted=True, cup=True), "I-1")
        assert 0.5 < sig.score < 1.0
        assert sig.rating == "Good"

    def test_not_permitted_score_0(self):
        sig = score_zoning_signal(_dc_params(permitted=False), "R-1")
        assert sig.score == 0.0
        assert sig.rating == "Poor"

    def test_unknown_permission_score_midrange(self):
        sig = score_zoning_signal(_dc_params(permitted=None), "?")
        assert 0.3 <= sig.score <= 0.7
        assert sig.rating == "Fair"

    def test_noise_limit_below_55_clamps_score(self):
        # Cooling towers produce 65–75 dB — a 50 dB limit is a constraint
        sig = score_zoning_signal(_dc_params(permitted=True, cup=False, noise=50.0), "I-1")
        assert sig.score <= 0.6  # clamped by noise constraint

    def test_noise_limit_above_65_does_not_penalize(self):
        sig_clean = score_zoning_signal(_dc_params(permitted=True, cup=False), "I-1")
        sig_noise = score_zoning_signal(_dc_params(permitted=True, cup=False, noise=70.0), "I-1")
        assert sig_noise.score == sig_clean.score  # no penalty above threshold


# ---------------------------------------------------------------------------
# compute_composite_score
# ---------------------------------------------------------------------------


class TestCompositeScore:
    def test_all_perfect_scores_returns_1(self):
        score, rating = compute_composite_score(
            _signal("power_grid", 1.0),
            _signal("fiber", 1.0),
            _signal("flood_zone", 1.0),
            _signal("seismic", 1.0),
            _signal("zoning", 1.0),
        )
        assert score == 1.0
        assert rating == "Excellent"

    def test_zoning_disqualifier_returns_disqualified(self):
        # Zoning score of 0.0 should hard-disqualify the site
        score, rating = compute_composite_score(
            _signal("power_grid", 0.9),
            _signal("fiber", 0.9),
            _signal("flood_zone", 0.9),
            _signal("seismic", 0.9),
            _signal("zoning", 0.0),
        )
        assert score == 0.0
        assert rating == "Disqualified"

    def test_weighted_sum_is_correct(self):
        # power=0.25, fiber=0.20, flood=0.25, seismic=0.10, zoning=0.20
        score, _ = compute_composite_score(
            _signal("power_grid", 1.0),  # 0.25
            _signal("fiber", 1.0),  # 0.20
            _signal("flood_zone", 0.0),  # 0.00
            _signal("seismic", 1.0),  # 0.10
            _signal("zoning", 1.0),  # 0.20
        )
        expected = 0.25 + 0.20 + 0.00 + 0.10 + 0.20
        assert abs(score - expected) < 0.001

    def test_good_site_rating(self):
        _, rating = compute_composite_score(
            _signal("power_grid", 0.8),
            _signal("fiber", 0.8),
            _signal("flood_zone", 0.8),
            _signal("seismic", 0.8),
            _signal("zoning", 0.8),
        )
        assert rating in ("Good", "Excellent")

    def test_poor_site_rating(self):
        _, rating = compute_composite_score(
            _signal("power_grid", 0.2),
            _signal("fiber", 0.2),
            _signal("flood_zone", 0.2),
            _signal("seismic", 0.2),
            _signal("zoning", 0.5),  # must be > 0 to avoid Disqualified
        )
        assert rating == "Poor"


# ---------------------------------------------------------------------------
# Flood zone scores — boundary values
# ---------------------------------------------------------------------------


class TestFloodZoneScores:
    def test_zone_x_is_best(self):
        score, rating = _FLOOD_ZONE_SCORES["X"]
        assert score == 1.0
        assert rating == "Excellent"

    def test_zone_ae_is_poor(self):
        score, rating = _FLOOD_ZONE_SCORES["AE"]
        assert score < 0.5
        assert rating == "Poor"

    def test_zone_x500_is_good(self):
        score, rating = _FLOOD_ZONE_SCORES["X500"]
        assert 0.7 <= score <= 0.95
        assert rating in ("Good", "Excellent")


# ---------------------------------------------------------------------------
# Seismic scores — boundary values
# ---------------------------------------------------------------------------


class TestSeismicScores:
    def test_very_low_is_best(self):
        score, rating = _SEISMIC_SCORES["very_low"]
        assert score == 1.0
        assert rating == "Excellent"

    def test_very_high_is_worst(self):
        score, rating = _SEISMIC_SCORES["very_high"]
        assert score <= 0.15
        assert rating == "Poor"


# ---------------------------------------------------------------------------
# run_datacenter_pipeline — integration unit test (mocked I/O)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_datacenter_pipeline_returns_scorecard():
    """run_datacenter_pipeline should return a SiteScorecard with all signals populated."""
    mock_prop = PropertyRecord(
        address="1000 Industrial Blvd",
        municipality="Miami Gardens",
        county="Miami-Dade",
        zoning_code="I-1",
    )

    good_signal = InfraSignal(
        name="power_grid",
        label="Grid Access",
        score=0.9,
        rating="Excellent",
        summary="Good grid access.",
        raw_value="FPL — $0.10/kWh",
        source="NREL",
        confidence="high",
    )

    with (
        patch(
            "plotlot.pipeline.datacenter.fetch_power_signal",
            new_callable=AsyncMock,
            return_value=good_signal,
        ),
        patch(
            "plotlot.pipeline.datacenter.fetch_fiber_signal",
            new_callable=AsyncMock,
            return_value=InfraSignal(
                name="fiber",
                label="Fiber",
                score=0.8,
                rating="Good",
                summary="1 fiber provider.",
                raw_value="1 provider",
                source="FCC",
                confidence="high",
            ),
        ),
        patch(
            "plotlot.pipeline.datacenter.fetch_flood_signal",
            new_callable=AsyncMock,
            return_value=InfraSignal(
                name="flood_zone",
                label="Flood Zone",
                score=1.0,
                rating="Excellent",
                summary="Zone X.",
                raw_value="X",
                source="FEMA",
                confidence="high",
            ),
        ),
        patch(
            "plotlot.pipeline.datacenter.fetch_seismic_signal",
            new_callable=AsyncMock,
            return_value=InfraSignal(
                name="seismic",
                label="Seismic",
                score=0.95,
                rating="Excellent",
                summary="Very low.",
                raw_value="Ss=0.05g",
                source="USGS",
                confidence="high",
            ),
        ),
        patch(
            "plotlot.pipeline.datacenter.extract_datacenter_params",
            new_callable=AsyncMock,
            return_value=DataCenterParams(
                zoning_code="I-1",
                is_industrial_permitted=True,
                conditional_use_required=False,
            ),
        ),
        patch(
            "plotlot.pipeline.datacenter.generate_site_summary",
            new_callable=AsyncMock,
            return_value=(
                "Excellent site for data center development.",
                [],
                ["Zone X flood protection", "As-of-right industrial zoning"],
            ),
        ),
    ):
        from plotlot.pipeline.datacenter import run_datacenter_pipeline

        result = await run_datacenter_pipeline(
            address="1000 Industrial Blvd, Miami Gardens, FL",
            property_record=mock_prop,
            lat=25.957,
            lng=-80.199,
            municipality="Miami Gardens",
            county="Miami-Dade",
            zoning_results=[],
        )

    assert isinstance(result, SiteScorecard)
    assert result.composite_score > 0.7
    assert result.composite_rating in ("Good", "Excellent")
    assert result.power_signal is not None
    assert result.fiber_signal is not None
    assert result.flood_signal is not None
    assert result.seismic_signal is not None
    assert result.zoning_signal is not None
    assert result.datacenter_params is not None
    assert result.summary != ""
    assert len(result.strengths) > 0


@pytest.mark.asyncio
async def test_run_datacenter_pipeline_disqualified_on_bad_zoning():
    """When zoning prohibits data centers, composite_rating must be Disqualified."""
    mock_prop = PropertyRecord(
        address="123 Main St",
        municipality="Miami Gardens",
        county="Miami-Dade",
        zoning_code="R-1",
    )

    with (
        patch(
            "plotlot.pipeline.datacenter.fetch_power_signal",
            new_callable=AsyncMock,
            return_value=_signal("power_grid", 0.9),
        ),
        patch(
            "plotlot.pipeline.datacenter.fetch_fiber_signal",
            new_callable=AsyncMock,
            return_value=_signal("fiber", 0.9),
        ),
        patch(
            "plotlot.pipeline.datacenter.fetch_flood_signal",
            new_callable=AsyncMock,
            return_value=_signal("flood_zone", 1.0),
        ),
        patch(
            "plotlot.pipeline.datacenter.fetch_seismic_signal",
            new_callable=AsyncMock,
            return_value=_signal("seismic", 0.95),
        ),
        patch(
            "plotlot.pipeline.datacenter.extract_datacenter_params",
            new_callable=AsyncMock,
            return_value=DataCenterParams(
                zoning_code="R-1",
                is_industrial_permitted=False,  # Residential zone — not permitted
            ),
        ),
        patch(
            "plotlot.pipeline.datacenter.generate_site_summary",
            new_callable=AsyncMock,
            return_value=(
                "Site disqualified — residential zone.",
                ["Not permitted in R-1"],
                [],
            ),
        ),
    ):
        from plotlot.pipeline.datacenter import run_datacenter_pipeline

        result = await run_datacenter_pipeline(
            address="123 Main St, Miami Gardens, FL",
            property_record=mock_prop,
            lat=25.9,
            lng=-80.2,
            municipality="Miami Gardens",
            county="Miami-Dade",
            zoning_results=[],
        )

    assert result.composite_rating == "Disqualified"
    assert result.composite_score == 0.0
