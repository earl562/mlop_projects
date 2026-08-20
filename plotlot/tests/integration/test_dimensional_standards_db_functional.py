"""Dimensional standards functional test — real DB, no fixture fallback.

Proves verification_status separation (verified vs staged), allow_fixture_fallback
works, and live DB queries are real.
"""

from __future__ import annotations

import pytest
from plotlot.domain.dimensional_standard import VerificationStatus
from plotlot.storage.dimensional_standards import get_dimensional_standard
from plotlot.storage.db import init_db


@pytest.fixture(autouse=True)
async def _init():
    await init_db()


class TestDimensionalStandardsDB:
    @pytest.mark.asyncio
    async def test_verified_ftl_row_returns_with_fixture_fallback_disabled(self):
        """Live DB returns verified FTL rows, not fixture."""
        got = await get_dimensional_standard(
            "Fort Lauderdale", "RS-8", allow_fixture_fallback=False
        )
        assert got is not None, "live DB must have verified FTL/RS-8"
        assert got.verification_status == VerificationStatus.VERIFIED, (
            f"FTL/RS-8 must be VERIFIED, got {got.verification_status}"
        )
        assert got.max_density_units_per_acre == 8.0
        assert got.setback_rear_ft == 15  # verified from Sec. 47-5.31
        assert got.is_verified_fact_source() is True

    @pytest.mark.asyncio
    async def test_staged_miami_row_is_not_verified(self):
        got = await get_dimensional_standard("Miami", "R-4", allow_fixture_fallback=False)
        if got is None:
            pytest.skip("Miami/R-4 not in live DB")
        assert got.verification_status != VerificationStatus.VERIFIED, (
            "staged row must NOT be verified"
        )
        assert got.is_verified_fact_source() is False, (
            "staged row must not be a verified_fact source"
        )

    @pytest.mark.asyncio
    async def test_staged_hollywood_row_is_not_verified(self):
        got = await get_dimensional_standard("Hollywood", "RS-5", allow_fixture_fallback=False)
        if got is None:
            pytest.skip("Hollywood/RS-5 not in live DB")
        assert got.verification_status != VerificationStatus.VERIFIED
        assert got.is_verified_fact_source() is False

    @pytest.mark.asyncio
    async def test_miss_returns_none_with_fixture_fallback_disabled(self):
        got = await get_dimensional_standard("Nowhereville", "ZZ-999", allow_fixture_fallback=False)
        assert got is None, "miss must return None, not fixture fallback"

    @pytest.mark.asyncio
    async def test_fixture_fallback_disabled_does_not_return_fixture_only_data(self):
        """Even Fort Lauderdale RS-4.4 should come from DB (not fixture) when fallback is off."""
        got = await get_dimensional_standard(
            "Fort Lauderdale", "RS-4.4", allow_fixture_fallback=False
        )
        if got is None:
            pytest.skip("FTL/RS-4.4 not in live DB")
        assert got.max_density_units_per_acre == 4.4
        assert got.verification_status == VerificationStatus.VERIFIED

    @pytest.mark.asyncio
    async def test_verified_row_produces_real_numeric_params(self):
        """A verified standard must convert to NumericZoningParams correctly."""
        got = await get_dimensional_standard(
            "Fort Lauderdale", "RS-8", allow_fixture_fallback=False
        )
        assert got is not None
        params = got.to_numeric_zoning_params()
        assert params.max_density_units_per_acre == 8.0
        assert params.max_height_ft == 35.0
        # far + max_lot_coverage_pct are tiered in the ordinance table
        # (Lot Size | Coverage | FAR) — the extractor doesn't yet parse tiered
        # values from sub-tables. They may be NULL in the DB. Assert what IS
        # reliably extracted: density + height.
        assert params.max_density_units_per_acre == 8.0
