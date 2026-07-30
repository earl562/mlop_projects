"""Live DB integration test: district_dimensional_standards serves real verified
South FL zoning data (Slice 3.2, criterion 4).

MARKED live — requires the local PostgreSQL DB (Homebrew postgresql@16 on
:5432) populated with the seed script. Skipped in the deterministic local gate
(which runs without a populated DB); run explicitly when touching dimensional
storage or before any claim that "the verified-fact path works for South FL":

    PLOTLOT_LIVE_TESTS=1 uv run pytest tests/integration/test_dimensional_standards_live.py -v

Populate the DB first:
    uv run python scripts/seed_dimensional_standards.py

This is the evidence test required by the CLAIM-WITHOUT-EVIDENCE GUARD: a unit
test passing against the fixture store is not evidence the live DB path works.
This test runs get_dimensional_standard against the real DB table and asserts
real, verified values come back with provenance.
"""

from __future__ import annotations

import os

import pytest

from plotlot.domain.dimensional_standard import DistrictDimensionalStandard
from plotlot.storage.dimensional_standards import get_dimensional_standard

_LIVE = os.environ.get("PLOTLOT_LIVE_TESTS") == "1"
pytestmark = pytest.mark.skipif(
    not _LIVE, reason="set PLOTLOT_LIVE_TESTS=1 + run scripts/seed_dimensional_standards.py"
)

# Real verified (municipality, district_code, max_density_units_per_acre) triples.
# Fort Lauderdale values are VERIFIED against the ingested ordinance corpus
# (ordinance_chunks rows). Miami/Hollywood are STAGED (hand-entered, assumption-
# grade) pending Phase 9 ingestion — their source_section_id carries "STAGED:".
SOUTH_FL_PROBES = [
    # Fort Lauderdale — verified against Sec. 47-5.31 / 47-5.30 / 47-5.34
    ("Fort Lauderdale", "RS-8", 8.0),
    ("Fort Lauderdale", "RS-4.4", 4.4),  # NOTE: real code is RS-4.4, not RS-4
    ("Fort Lauderdale", "RM-15", 15.0),
    # Miami — STAGED (not yet verified against ingested text)
    ("Miami", "R-1", 5.8),
    ("Miami", "R-3", 17.4),
    ("Miami", "R-4", 43.5),
    # Hollywood — STAGED
    ("Hollywood", "RS-5", 5.0),
    ("Hollywood", "RM-15", 15.0),
    ("Hollywood", "RM-25", 25.0),
]

NUMERIC_FIELDS = (
    "min_lot_area_sqft",
    "min_lot_width_ft",
    "setback_front_ft",
    "setback_side_ft",
    "setback_rear_ft",
    "max_height_ft",
    "max_lot_coverage_pct",
    "far",
    "max_density_units_per_acre",
)


@pytest.mark.asyncio
async def test_live_db_serves_verified_south_fl_dimensional_standards():
    """The live district_dimensional_standards table returns the verified rows
    for all 3 South FL municipalities with real density values."""
    for municipality, district_code, expected_density in SOUTH_FL_PROBES:
        got = await get_dimensional_standard(
            municipality, district_code, allow_fixture_fallback=False
        )
        assert got is not None, f"live DB miss for {municipality}/{district_code}"
        assert isinstance(got, DistrictDimensionalStandard)
        assert got.municipality == municipality
        assert got.district_code == district_code
        assert got.max_density_units_per_acre == pytest.approx(expected_density), (
            f"{municipality}/{district_code}: density {got.max_density_units_per_acre} "
            f"!= verified {expected_density}"
        )
        # Provenance: every verified-fact row names its ordinance section.
        assert got.source_section_id, f"{municipality}/{district_code}: missing source_section_id"
        assert got.source_url, f"{municipality}/{district_code}: missing source_url"
        # Source-boundary honesty: Fort Lauderdale rows are VERIFIED against
        # the ingested ordinance corpus (source_section_id starts with "Sec.");
        # Miami/Hollywood are honestly marked STAGED (assumption-grade) pending
        # Phase 9 ingestion. A STAGED row must never claim to be verified.
        if municipality == "Fort Lauderdale":
            assert got.source_section_id.startswith("Sec."), (
                f"{municipality}/{district_code}: expected verified source section, "
                f"got {got.source_section_id!r}"
            )
        else:
            assert got.source_section_id.startswith("STAGED:"), (
                f"{municipality}/{district_code}: expected STAGED marker, "
                f"got {got.source_section_id!r}"
            )


@pytest.mark.asyncio
async def test_live_db_at_least_one_municipality_has_3_districts_all_numeric():
    """Criterion 4: >=1 municipality returns rows with ALL numeric fields
    populated for >=3 districts — exercised against the LIVE DB table, not the
    fixture fallback."""
    for municipality in ("Fort Lauderdale", "Miami", "Hollywood"):
        district_codes = {
            "Fort Lauderdale": ("RS-8", "RS-4.4", "RM-15"),
            "Miami": ("R-1", "R-3", "R-4"),
            "Hollywood": ("RS-5", "RM-15", "RM-25"),
        }[municipality]
        fully_populated = 0
        for code in district_codes:
            got = await get_dimensional_standard(municipality, code, allow_fixture_fallback=False)
            if got is None:
                continue
            if all(getattr(got, f) is not None for f in NUMERIC_FIELDS):
                fully_populated += 1
        assert fully_populated >= 3, (
            f"{municipality}: expected >=3 fully-numeric districts in live DB, "
            f"got {fully_populated}"
        )


@pytest.mark.asyncio
async def test_live_db_miss_returns_none():
    """A (municipality, district_code) not in the table returns None — the
    contract that lets lookup.py fall through to LLM extraction."""
    got = await get_dimensional_standard("Nonexistent Town", "ZZ-999", allow_fixture_fallback=False)
    assert got is None
