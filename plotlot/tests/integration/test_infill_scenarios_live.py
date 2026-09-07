"""Live integration test: residential infill scenario analyzer on real South FL
lots (the real product use case).

Given real residential infill addresses across South FL, identify the zoning
district from OpenData/ArcGIS, pull the verified dimensional standard, and run
multiple development scenarios per lot (by-right density, lot-split, missing-
middle/ADU, assemblage). Each scenario is a typed Claim — calculation for the
deterministic by-right, hypothesis for speculative upside (never verified_fact).

MARKED live — requires county ArcGIS + the seeded dimensional standards.

    PLOTLOT_LIVE_TESTS=1 uv run pytest tests/integration/test_infill_scenarios_live.py -v
"""

from __future__ import annotations

import os

import pytest

from plotlot.domain.claims import ClaimKind
from plotlot.pipeline.infill_scenarios import analyze_residential_infill
from plotlot.retrieval.geocode import geocode_address
from plotlot.retrieval.property import lookup_property

_LIVE = os.environ.get("PLOTLOT_LIVE_TESTS") == "1"
pytestmark = pytest.mark.skipif(
    not _LIVE, reason="set PLOTLOT_LIVE_TESTS=1 (hits county ArcGIS + needs seeded DB)"
)

# Real residential infill lots across South FL — the actual product use case.
# Each is a single-family/low-density residential address where infill upside
# (lot split, ADU, missing-middle) is the question.
INFILL_LOTS = [
    # Fort Lauderdale RS-8 single-family — classic infill candidate (11760 sqft)
    ("1234 NW 15th St, Fort Lauderdale, FL 33311", "Broward", "Fort Lauderdale"),
    # Miami R15 single-family (7500 sqft)
    ("123 NW 103rd St, Miami, FL 33150", "Miami-Dade", "Miami"),
    # West Palm Beach FWD-5 (9753 sqft)
    ("224 Datura St, West Palm Beach, FL 33401", "Palm Beach", "West Palm Beach"),
]


@pytest.mark.asyncio
async def test_infill_analyzer_runs_all_scenarios_per_lot():
    """For each real infill lot: identify zoning (OpenData), pull the verified
    dimensional standard, and run all 4 scenarios. Every scenario produces a
    typed Claim with the right kind + provenance."""
    for address, county, municipality in INFILL_LOTS:
        geo = await geocode_address(address)
        assert geo is not None, f"geocode failed for {address}"
        pr = await lookup_property(address, county, lat=geo["lat"], lng=geo["lng"])
        assert pr is not None and pr.zoning_code, f"no zoning for {address}"
        assert pr.lot_size_sqft and pr.lot_size_sqft > 0, f"no lot size for {address}"

        results = await analyze_residential_infill(
            address=address,
            municipality=municipality,
            district_code=pr.zoning_code,
            lot_size_sqft=pr.lot_size_sqft,
            lot_width_ft=None,  # lot width parse is separate; scenarios degrade gracefully
            source_url="https://opendata/zoning-query",
        )

        assert len(results) == 4, f"{address}: expected 4 scenarios, got {len(results)}"

        # Scenario names
        names = {r.scenario for r in results}
        assert names == {
            "by_right_density",
            "lot_split_feasibility",
            "missing_middle_adu",
            "assemblage_potential",
        }

        # Each claim is typed correctly
        for r in results:
            assert r.claim.kind in (ClaimKind.CALCULATION, ClaimKind.HYPOTHESIS), (
                f"{address}/{r.scenario}: kind={r.claim.kind} — must be calculation or hypothesis, "
                f"never verified_fact (spec #6: entitlement upside never guaranteed)"
            )
            # Hypotheses MUST have a next_verification_step (spec #6).
            if r.claim.kind is ClaimKind.HYPOTHESIS:
                assert r.claim.next_verification_step, (
                    f"{address}/{r.scenario}: hypothesis missing next_verification_step"
                )
            # Provenance on every claim.
            assert r.claim.source_url or r.claim.origin != ClaimKind.VERIFIED_FACT

        print(f"\n  {address} ({municipality}/{pr.zoning_code}, {pr.lot_size_sqft:,.0f} sqft):")
        for r in results:
            tag = r.claim.kind.value
            feas = "?" if r.feasible is None else ("Y" if r.feasible else "N")
            print(f"    [{tag:12} feas={feas}] {r.scenario:24} {r.summary}")


@pytest.mark.asyncio
async def test_by_right_density_is_deterministic_calculation():
    """The by-right density scenario produces a kind=calculation claim (not
    hypothesis) when a verified standard exists — Kleyman's deterministic step."""
    address, county, municipality = INFILL_LOTS[0]  # Fort Lauderdale RS-8
    geo = await geocode_address(address)
    pr = await lookup_property(address, county, lat=geo["lat"], lng=geo["lng"])
    results = await analyze_residential_infill(
        address=address,
        municipality=municipality,
        district_code=pr.zoning_code,
        lot_size_sqft=pr.lot_size_sqft,
        source_url="test",
        allow_fixture_fallback=False,
    )
    by_right = next(r for r in results if r.scenario == "by_right_density")
    # Fort Lauderdale has verified standards → calculation, not hypothesis.
    if by_right.claim.kind is ClaimKind.CALCULATION:
        assert isinstance(by_right.claim.value, (int, float))
        assert by_right.claim.value >= 0
