"""Chunk corroboration and the coverage guard.

The permanence half of the fix. Populating San Diego makes San Diego correct
today; these two behaviours are what stop the table from silently emptying out
again for the next city:

* corroboration — a district whose occurrences disagree is EXCLUDED, never
  guessed at, because a wrong deterministic row is worse than no row;
* ``check_standards_coverage`` — names every municipality whose density is still
  LLM-derived, so "the table is empty" can never again be invisible.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from plotlot.domain.dimensional_standard import VerificationStatus
from plotlot.ingestion import standards_extraction as se

_DENSITY = (
    "• {code} permits a maximum density of 1 dwelling unit for each {n} square feet of lot area"
)


def _chunk(text: str, section: str = "Art.01 Div.04", county: str = "San Diego"):
    return (text, section, county)


def _mock_session(chunks):
    session = MagicMock()
    session.execute = AsyncMock(return_value=MagicMock(all=MagicMock(return_value=chunks)))
    session.close = AsyncMock()
    return session


async def _extract(chunks, **kw):
    with patch.object(se, "get_session", new=AsyncMock(return_value=_mock_session(chunks))):
        return await se.extract_standards_for_municipality("San Diego", state="CA", **kw)


class TestCorroboration:
    @pytest.mark.asyncio
    async def test_agreeing_occurrences_become_one_verified_row(self):
        """Chunks overlap, so the same sentence recurs. Agreement IS the cross-check."""
        chunks = [
            _chunk(_DENSITY.format(code="RM-3-7", n="1,000")),
            _chunk(_DENSITY.format(code="RM-3-7", n="1,000")),
            _chunk(_DENSITY.format(code="RM-3-7", n="1,000")),
        ]
        rows, report = await _extract(chunks)
        assert len(rows) == 1
        assert rows[0].district_code == "RM-3-7"
        assert rows[0].min_lot_area_sqft == 1000.0
        assert rows[0].verification_status is VerificationStatus.VERIFIED
        assert report.conflicted == ()

    @pytest.mark.asyncio
    async def test_disagreeing_occurrences_are_excluded_not_resolved(self):
        """THE safety property. Two different numbers for one district means we do
        not know the answer. Picking one — most common, first seen, whatever —
        would produce a confidently wrong deterministic standard."""
        chunks = [
            _chunk(_DENSITY.format(code="RM-3-7", n="1,000")),
            _chunk(_DENSITY.format(code="RM-3-7", n="1,000")),
            _chunk(_DENSITY.format(code="RM-3-7", n="600")),
        ]
        rows, report = await _extract(chunks)
        assert rows == []
        assert report.conflicted == ("RM-3-7",)
        assert "RM-3-7" not in report.values

    @pytest.mark.asyncio
    async def test_one_districts_conflict_does_not_poison_the_others(self):
        chunks = [
            _chunk(_DENSITY.format(code="RM-3-7", n="1,000")),
            _chunk(_DENSITY.format(code="RM-3-7", n="600")),
            _chunk(_DENSITY.format(code="RM-2-5", n="1,500")),
        ]
        rows, report = await _extract(chunks)
        assert [r.district_code for r in rows] == ["RM-2-5"]
        assert report.conflicted == ("RM-3-7",)

    @pytest.mark.asyncio
    async def test_density_governed_districts_are_excluded(self):
        """Caught during validation of real Escondido data.

        `| R-3 | 6,000 | 60 | 18 du/acre |` — 6,000 is the minimum LOT SIZE, not
        the per-unit area. The table extractor captured the area but missed the
        density column, so storing it would compute 4 units on a 24,000 sqft lot
        where the ordinance allows 9. A district whose own line advertises a
        du/acre density we did not capture is proof that area is the wrong basis.
        """
        chunks = [
            _chunk(
                "| Zone | Min Lot Area | Min Width |\n| --- | --- | --- |\n| R-3 | 6,000 | 60 | 18 du/acre |"
            )
        ]
        rows, report = await _extract(chunks)
        assert rows == []
        assert report.density_governed == ("R-3",)
        assert "R-3" not in report.values

    @pytest.mark.asyncio
    async def test_area_governed_districts_are_kept_alongside_density_governed_ones(self):
        """One multi-family zone must not disqualify the single-family zones in the
        same table — Escondido keeps its 10 R-1-N rows and drops only R-2..R-5."""
        chunks = [
            _chunk(
                "| Zone | Min Lot Area | Min Width |\n| --- | --- | --- |\n"
                "| R-1-10 | 10,000 | 80 |\n"
                "| R-3 | 6,000 | 60 | 18 du/acre |"
            )
        ]
        rows, report = await _extract(chunks)
        assert [r.district_code for r in rows] == ["R-1-10"]
        assert report.density_governed == ("R-3",)

    @pytest.mark.asyncio
    async def test_a_per_unit_area_statement_is_not_treated_as_density_governed(self):
        """San Diego states 'per N square feet of lot area', which IS the per-unit
        basis. It must not be swept up by the du/acre guard."""
        chunks = [_chunk(_DENSITY.format(code="RM-3-7", n="1,000"))]
        rows, report = await _extract(chunks)
        assert [r.district_code for r in rows] == ["RM-3-7"]
        assert report.density_governed == ()

    @pytest.mark.asyncio
    async def test_no_chunks_yields_an_empty_report_not_an_error(self):
        rows, report = await _extract([])
        assert rows == []
        assert report.districts_found == 0
        assert report.ok is False


class TestBackfillPersistence:
    @pytest.mark.asyncio
    async def test_dry_run_extracts_but_writes_nothing(self):
        chunks = [_chunk(_DENSITY.format(code="RM-3-7", n="1,000"))]
        store = AsyncMock(return_value=1)
        with (
            patch.object(se, "get_session", new=AsyncMock(return_value=_mock_session(chunks))),
            patch.object(se, "store_dimensional_standards", new=store),
        ):
            report = await se.backfill_dimensional_standards("San Diego", state="CA", dry_run=True)
        store.assert_not_awaited()
        assert report.districts_found == 1
        assert report.rows_written == 0

    @pytest.mark.asyncio
    async def test_backfill_persists_and_reports_the_written_count(self):
        chunks = [_chunk(_DENSITY.format(code="RM-3-7", n="1,000"))]
        store = AsyncMock(return_value=1)
        with (
            patch.object(se, "get_session", new=AsyncMock(return_value=_mock_session(chunks))),
            patch.object(se, "store_dimensional_standards", new=store),
        ):
            report = await se.backfill_dimensional_standards("San Diego", state="CA")
        store.assert_awaited_once()
        assert report.rows_written == 1


class TestCoverageGuard:
    @pytest.mark.asyncio
    async def test_reports_municipalities_with_chunks_but_no_standards(self):
        """The alarm that was missing for months. The table held zero rows while
        every layer above it behaved as if it were populated."""
        session = MagicMock()
        session.execute = AsyncMock(
            side_effect=[
                MagicMock(all=MagicMock(return_value=[("San Diego", 2910), ("Poway", 765)])),
                MagicMock(all=MagicMock(return_value=[("San Diego", 34)])),
            ]
        )
        session.close = AsyncMock()
        with patch.object(se, "get_session", new=AsyncMock(return_value=session)):
            gaps = await se.check_standards_coverage()

        assert [g.municipality for g in gaps] == ["Poway"]
        assert gaps[0].chunk_count == 765
        assert gaps[0].standard_count == 0

    @pytest.mark.asyncio
    async def test_full_coverage_reports_no_gaps(self):
        session = MagicMock()
        session.execute = AsyncMock(
            side_effect=[
                MagicMock(all=MagicMock(return_value=[("San Diego", 2910)])),
                MagicMock(all=MagicMock(return_value=[("San Diego", 34)])),
            ]
        )
        session.close = AsyncMock()
        with patch.object(se, "get_session", new=AsyncMock(return_value=session)):
            assert await se.check_standards_coverage() == []
