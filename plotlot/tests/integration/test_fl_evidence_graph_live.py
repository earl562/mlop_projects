"""Slice 3.5 live integration test: Fort Lauderdale evidence graph is complete.

Pins the 3.5 acceptance criteria:
  * For Fort Lauderdale: every residential district has a DistrictDimensionalStandard,
    every ingested section has path + cross_refs populated, freshness computable (criterion 1).
  * Live verification: a query for RS-8 setbacks returns the typed standard, not LLM (criterion 2).
  * Integration test pins the FL evidence graph is complete (criterion 3).

MARKED live — requires the local PostgreSQL DB populated by the seed + backfill
scripts. Skipped in the deterministic local gate.

    PLOTLOT_LIVE_TESTS=1 uv run pytest tests/integration/test_fl_evidence_graph_live.py -v

Populate first:
    uv run python scripts/seed_dimensional_standards.py
    uv run python scripts/backfill_ordinance_sections.py "Fort Lauderdale"
"""

from __future__ import annotations

import os

import pytest

from plotlot.domain.dimensional_standard import DistrictDimensionalStandard
from plotlot.storage.dimensional_standards import get_dimensional_standard

_LIVE = os.environ.get("PLOTLOT_LIVE_TESTS") == "1"
pytestmark = pytest.mark.skipif(
    not _LIVE, reason="set PLOTLOT_LIVE_TESTS=1 + run seed + backfill scripts"
)


@pytest.mark.asyncio
async def test_fl_residential_districts_have_typed_standards():
    """Criterion 1: every FL residential district (RS-8, RS-4.4, RM-15) has a
    DistrictDimensionalStandard in the live DB with verified values."""
    for district_code, expected_density in [("RS-8", 8.0), ("RS-4.4", 4.4), ("RM-15", 15.0)]:
        got = await get_dimensional_standard(
            "Fort Lauderdale", district_code, allow_fixture_fallback=False
        )
        assert got is not None, f"FL/{district_code}: no typed standard in live DB"
        assert got.max_density_units_per_acre == pytest.approx(expected_density)
        # Provenance: verified against the ingested ordinance corpus.
        assert got.source_section_id.startswith("Sec."), (
            f"FL/{district_code}: expected verified source section, got {got.source_section_id!r}"
        )


@pytest.mark.asyncio
async def test_rs8_setbacks_query_returns_typed_standard_not_llm():
    """Criterion 2: a query for RS-8 setbacks returns the typed standard with
    the verified rear setback (15 ft, from Sec. 47-5.31), not an LLM extraction.
    This is the verified-fact fast path the calculator consumes."""
    got = await get_dimensional_standard("Fort Lauderdale", "RS-8", allow_fixture_fallback=False)
    assert got is not None
    assert isinstance(got, DistrictDimensionalStandard)
    # Verified values from Sec. 47-5.31 (ordinance_chunks id=3755).
    assert got.setback_rear_ft == 15  # NOT 25 (25 is only when abutting waterway)
    assert got.setback_front_ft == 25
    assert got.far == 0.75  # at the ≤7,500 sf tier (not 0.50)
    assert got.max_lot_coverage_pct == 50  # at ≤7,500 sf (not 40)
    assert got.source_section_id.startswith("Sec. 47-5.31")


@pytest.mark.asyncio
async def test_fl_sections_have_path_and_cross_refs():
    """Criterion 1: every ingested FL section has path + cross_refs populated
    in ordinance_sections (the structural index / evidence graph)."""
    from sqlalchemy import text
    from plotlot.storage.db import get_session

    session = await get_session()
    try:
        result = await session.execute(
            text("""
            SELECT count(*) AS total,
                   count(path) AS with_path,
                   count(cross_refs) AS with_xrefs,
                   count(section_type) AS with_type,
                   count(*) FILTER (WHERE array_length(cross_refs,1) > 0) AS with_nonempty_xrefs
            FROM ordinance_sections
            WHERE municipality = 'Fort Lauderdale'
        """)
        )
        row = result.one()
        total, with_path, with_xrefs, with_type, with_nonempty = row
        assert total > 0, "FL has no sections in ordinance_sections (run backfill)"
        assert with_path == total, f"FL: {total - with_path} sections missing path"
        assert with_xrefs == total, f"FL: {total - with_xrefs} sections missing cross_refs"
        assert with_type == total, f"FL: {total - with_type} sections missing section_type"
        # At least the dimensional tables must have cross_refs (district codes).
        assert with_nonempty > 0, "FL: no section has non-empty cross_refs"
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_fl_dimensional_tables_section_type_classified():
    """The RS-8 / RS-4.4 / RM-15 sections are classified as dimensional_table
    in the structural index (so the extractor + freshness can find them)."""
    from sqlalchemy import text
    from plotlot.storage.db import get_session

    session = await get_session()
    try:
        result = await session.execute(
            text("""
            SELECT section_number, section_type
            FROM ordinance_sections
            WHERE municipality = 'Fort Lauderdale'
              AND section_number IN ('Sec. 47-5.30.', 'Sec. 47-5.31.', 'Sec. 47-5.34.')
            ORDER BY section_number
        """)
        )
        rows = result.all()
        assert len(rows) == 3, f"expected 3 FL residential dimensional sections, got {len(rows)}"
        for sec_num, sec_type in rows:
            assert sec_type == "dimensional_table", (
                f"FL/{sec_num}: expected dimensional_table, got {sec_type}"
            )
    finally:
        await session.close()


@pytest.mark.asyncio
async def test_freshness_computed_on_fl_dimensional_claim():
    """Criterion 1: freshness is computable on a claim derived from an FL
    dimensional standard (the 3.4 freshness seam works against real verified
    data). A claim built from a freshly-scraped standard is FRESH and satisfies
    the verified_fact prerequisite."""
    from datetime import datetime, timezone
    from plotlot.domain.claims import Claim, ClaimFreshness, ClaimKind, ClaimOrigin

    got = await get_dimensional_standard("Fort Lauderdale", "RS-8", allow_fixture_fallback=False)
    assert got is not None
    # Build a claim with fresh freshness (scraped today, amended earlier).
    now_iso = datetime.now(timezone.utc).isoformat()
    claim = Claim(
        field_key="zoning.district",
        value=got.district_code,
        kind=ClaimKind.VERIFIED_FACT,
        origin=ClaimOrigin.LOCAL_AUTHORITY,
        source_url=got.source_url,
        metadata={"amended_date": "2026-01-01T00:00:00", "scraped_at": now_iso},
    )
    assert claim.freshness is ClaimFreshness.FRESH
    assert claim.satisfies_verified_fact_prerequisite() is True
