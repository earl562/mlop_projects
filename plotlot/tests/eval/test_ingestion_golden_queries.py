"""Golden-query ingestion eval (Slice 3.6).

The verification gate inside the autonomous-ingestion skill: after ingest, a
golden set of queries ("what is the RS-8 setback?") must return the typed
DistrictDimensionalStandard row with verified values. Hit-rate >= 90% or the
ingest is botched (detectable, not shipped silently).

Run:
    PLOTLOT_LIVE_TESTS=1 uv run pytest tests/eval/test_ingestion_golden_queries.py -v

Golden queries are (municipality, district_code, expected_field, expected_value)
tuples drawn from the VERIFIED Fort Lauderdale values (Sec. 47-5.30/.31/.34 in
the ingested ordinance corpus). A hit = the typed standard is present AND the
queried field matches the verified value. A miss = no typed row OR wrong value.

The gate fails below 90% hit-rate — that's the "botched ingest detectable"
criterion: a re-ingestion that drops rows or mangles values shows up as a
hit-rate drop, not a silent regression.
"""

from __future__ import annotations

import os

import pytest

from plotlot.storage.dimensional_standards import get_dimensional_standard

_LIVE = os.environ.get("PLOTLOT_LIVE_TESTS") == "1"
pytestmark = pytest.mark.skipif(
    not _LIVE, reason="set PLOTLOT_LIVE_TESTS=1 + run scripts/seed_dimensional_standards.py"
)

# Golden queries: (municipality, district_code, field, expected_value).
# Fort Lauderdale values are VERIFIED against the ingested ordinance corpus
# (Sec. 47-5.31 = RS-8, Sec. 47-5.30 = RS-4.4, Sec. 47-5.34 = RM-15).
GOLDEN_QUERIES = [
    # RS-8 (Sec. 47-5.31, ordinance_chunks id=3755)
    ("Fort Lauderdale", "RS-8", "max_density_units_per_acre", 8.0),
    ("Fort Lauderdale", "RS-8", "setback_front_ft", 25.0),
    ("Fort Lauderdale", "RS-8", "setback_rear_ft", 15.0),  # NOT 25 (waterway only)
    ("Fort Lauderdale", "RS-8", "setback_side_ft", 5.0),
    ("Fort Lauderdale", "RS-8", "max_height_ft", 35.0),
    ("Fort Lauderdale", "RS-8", "min_lot_area_sqft", 6000.0),  # NOT 5445
    ("Fort Lauderdale", "RS-8", "far", 0.75),  # NOT 0.50
    ("Fort Lauderdale", "RS-8", "max_lot_coverage_pct", 50.0),  # NOT 40
    ("Fort Lauderdale", "RS-8", "min_lot_width_ft", 50.0),
    # RS-4.4 (Sec. 47-5.30, id=3752) — NOTE: real code is RS-4.4, not RS-4
    ("Fort Lauderdale", "RS-4.4", "max_density_units_per_acre", 4.4),
    ("Fort Lauderdale", "RS-4.4", "setback_side_ft", 10.0),
    ("Fort Lauderdale", "RS-4.4", "min_lot_area_sqft", 10000.0),
    # RM-15 (Sec. 47-5.34, id=3764)
    ("Fort Lauderdale", "RM-15", "max_density_units_per_acre", 15.0),
    ("Fort Lauderdale", "RM-15", "setback_rear_ft", 15.0),
    ("Fort Lauderdale", "RM-15", "setback_front_ft", 25.0),
]

HIT_RATE_THRESHOLD = 0.90


@pytest.mark.asyncio
async def test_golden_queries_hit_rate_above_threshold():
    """The golden-query hit-rate must be >= 90%. Below that = botched ingest.

    A hit = the typed standard is present AND the queried field matches the
    verified value. A miss = no typed row OR wrong value (silent regression
    from a bad re-ingest). This gate makes a botched ingest detectable.
    """
    hits = 0
    misses: list[str] = []
    for municipality, district_code, field, expected in GOLDEN_QUERIES:
        got = await get_dimensional_standard(
            municipality, district_code, allow_fixture_fallback=False
        )
        if got is None:
            misses.append(f"{municipality}/{district_code}: no typed row (MISS)")
            continue
        actual = getattr(got, field, None)
        if actual is None:
            misses.append(f"{municipality}/{district_code}.{field}: missing value (MISS)")
            continue
        if actual == pytest.approx(expected):
            hits += 1
        else:
            misses.append(
                f"{municipality}/{district_code}.{field}: got {actual}, expected {expected} (WRONG)"
            )

    hit_rate = hits / len(GOLDEN_QUERIES)
    detail = f"\n  hits={hits}/{len(GOLDEN_QUERIES)} hit_rate={hit_rate:.1%}\n"
    if misses:
        detail += "  misses:\n    " + "\n    ".join(misses)
    assert hit_rate >= HIT_RATE_THRESHOLD, (
        f"ingestion golden-query hit-rate {hit_rate:.1%} < {HIT_RATE_THRESHOLD:.0%} "
        f"threshold — botched ingest detected. {detail}"
    )


@pytest.mark.asyncio
async def test_golden_queries_no_silent_value_drift():
    """A stronger per-query check: NO golden query may return a wrong value
    (as opposed to a miss). A wrong value means a re-ingest silently changed a
    verified number — the most dangerous regression. Every hit must match."""
    wrong_values: list[str] = []
    for municipality, district_code, field, expected in GOLDEN_QUERIES:
        got = await get_dimensional_standard(
            municipality, district_code, allow_fixture_fallback=False
        )
        if got is None:
            continue  # miss handled by the hit-rate test
        actual = getattr(got, field, None)
        if actual is not None and actual != pytest.approx(expected):
            wrong_values.append(
                f"{municipality}/{district_code}.{field}: got {actual}, expected {expected}"
            )
    assert not wrong_values, (
        "silent value drift detected — a verified number changed:\n  " + "\n  ".join(wrong_values)
    )
