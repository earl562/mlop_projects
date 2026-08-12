"""Only VERIFIED standards may be served as verified facts.

`VerificationStatus` has always documented this rule — "Only VERIFIED rows may
serve as local_authority/verified-fact calculator input. STAGED rows are
assumption-grade and must never produce verified_fact claims" — but nothing
enforced it. `lookup.py` labels ANY standard it receives `origin="local_authority"`,
so an UNVERIFIED row reaching the calculator would be presented as verified fact.

That is the failure mode this whole effort exists to prevent: it would trade
visibly-flaky LLM output for a confidently wrong deterministic number, which is
strictly worse because nothing downstream flags it.
"""

from __future__ import annotations

import pytest

from plotlot.domain.dimensional_standard import (
    DistrictDimensionalStandard,
    VerificationStatus,
)
from plotlot.storage import dimensional_standards as ds


def _standard(status: VerificationStatus) -> DistrictDimensionalStandard:
    return DistrictDimensionalStandard(
        municipality="Testville",
        county="Test",
        state="CA",
        district_code="RM-9-9",
        min_lot_area_sqft=1000.0,
        source_section_id="test",
        verification_status=status,
    )


@pytest.fixture(autouse=True)
def _clean_fixture_store():
    ds.clear_dimensional_standard_fixtures()
    yield
    ds.clear_dimensional_standard_fixtures()


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [VerificationStatus.UNVERIFIED, VerificationStatus.STAGED])
async def test_non_verified_standards_are_not_served(status):
    """The gate. A STAGED or UNVERIFIED row must come back as None so the caller
    falls back to the LLM path — which is at least labelled an assumption."""
    ds.register_dimensional_standard_fixture(_standard(status))
    got = await ds.get_dimensional_standard("Testville", "RM-9-9")
    assert got is None, f"{status.value} row must not be served as a verified fact"


@pytest.mark.asyncio
async def test_verified_standards_are_served():
    ds.register_dimensional_standard_fixture(_standard(VerificationStatus.VERIFIED))
    got = await ds.get_dimensional_standard("Testville", "RM-9-9")
    assert got is not None
    assert got.district_code == "RM-9-9"
    assert got.is_verified_fact_source() is True


@pytest.mark.asyncio
async def test_the_staged_miami_seed_is_not_served_as_fact():
    """The shipped Miami/Hollywood seeds describe themselves as STAGED
    ('source_section_id carries STAGED:', corpora not yet ingested). Before the
    gate they were served and labelled local_authority anyway."""
    got = await ds.get_dimensional_standard("Miami", "R-1")
    assert got is None


@pytest.mark.asyncio
async def test_the_fort_lauderdale_reference_seed_still_works():
    """The gate must not break the reference municipality. Its rows cite the exact
    ingested chunk id they were cross-checked against, so they are genuinely
    VERIFIED and must keep serving."""
    got = await ds.get_dimensional_standard("Fort Lauderdale", "RS-8")
    assert got is not None
    assert got.verification_status is VerificationStatus.VERIFIED
    assert got.max_density_units_per_acre == 8.0
