"""Live integration test: find_comparables returns real comps for South FL (slice 1.2).

MARKED live — requires network access to county ArcGIS servers. Skipped in the
deterministic local gate (which has no network); run explicitly when touching
comps or before any claim that "comps work for South FL."

This is the evidence test required by the CLAIM-WITHOUT-EVIDENCE GUARD in
progress.txt: a unit test passing is not evidence the feature works. This test
runs the feature against a real address and asserts real, sane comps come back.
"""

from __future__ import annotations

import os

import pytest

from plotlot.core.types import PropertyRecord
from plotlot.pipeline.comps import find_comparables

_LIVE = os.environ.get("PLOTLOT_LIVE_TESTS") == "1"
pytestmark = pytest.mark.skipif(
    not _LIVE, reason="set PLOTLOT_LIVE_TESTS=1 to run live comps tests"
)


@pytest.mark.asyncio
async def test_palm_beach_comps_return_real_sales_with_prices_and_dates():
    """Palm Beach County: find_comparables returns ≥1 comp with a real price
    (> $1000, arms-length) and a parseable sale date, within the radius."""
    subject = PropertyRecord(
        address="Wellington FL test",
        county="Palm Beach",
        municipality="Wellington",
        lat=26.66,
        lng=-80.25,
        lot_size_sqft=43560,
    )
    result = await find_comparables(subject, state="FL", radius_miles=3.0, months=60, max_comps=5)
    assert result.comparables or result.unit_comparables, (
        f"no comps returned for Palm Beach; notes={result.notes}"
    )
    all_comps = list(result.comparables) + list(result.unit_comparables)
    for c in all_comps:
        # Real sale, not a $1 transfer or $0 placeholder.
        assert c.sale_price > 1000, f"comp price {c.sale_price} not arms-length"
        # Real date (parseable to YYYY-MM-DD by _parse_sale_date).
        assert len(c.sale_date) >= 10, f"comp date {c.sale_date!r} not parseable"
        # Within radius.
        assert c.distance_miles <= 3.0, f"comp distance {c.distance_miles} > 3.0mi"
