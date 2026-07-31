"""Spike contract: extract Fort Lauderdale §47-5.60 dimensional table (slice 1.1).

Architecture de-risk: can we parse a real dimensional-standards table into
typed DistrictDimensionalStandard rows at ingestion time, so the calculator
reads verified-fact rows instead of LLM-extracted NumericZoningParams?

If this spike passes: the verified-fact path (Phase 3 evidence engineering)
is real, and Phase 3 proceeds at full scope.
If it fails: dimensional extraction becomes per-publisher / AutoHarness-load-bearing,
and the build plan re-baselines.

This is the spike variant of the Ralph loop: contract test + minimal impl.
Throws away exploratory dead ends; keeps the test + the working extractor if green.
"""

from __future__ import annotations

from plotlot.domain.dimensional_standard import extract_dimensional_standards


# Representative Fort Lauderdale §47-5.60 "Schedule of District Regulations"
# residential rows, as the codifier adapter would emit after _normalize_zone_tables.
# Real ordinance text, abbreviated to the residential districts.
FL_47_5_60_TABLE = """
Sec. 47-5.60. - Schedule of district regulations.

| District | Min Lot Area (sqft) | Min Lot Width (ft) | Front Setback (ft) | Side Setback (ft) | Rear Setback (ft) | Max Height (ft) | Max Lot Coverage (%) | FAR | Max Density (du/acre) |
|---|---|---|---|---|---|---|---|---|---|
| RS-1 | 7,200 | 50 | 25 | 5 | 25 | 35 | 40 | 0.50 | 6.0 |
| RS-2 | 6,000 | 50 | 25 | 5 | 25 | 35 | 40 | 0.50 | 7.2 |
| RS-3 | 5,000 | 50 | 25 | 5 | 25 | 35 | 45 | 0.60 | 8.7 |
| RS-4 | 4,500 | 50 | 25 | 5 | 25 | 35 | 45 | 0.60 | 9.6 |
| RM-15 | 3,000 | 40 | 20 | 5 | 20 | 40 | 50 | 0.75 | 15.0 |
"""

FL_SOURCE_SECTION_ID = "fl_fort_lauderdale_47_5_60"
FL_SOURCE_URL = "https://www.municode.com/library/fl/fort_lauderdale/code/ordinance?nodeId=ORTO_CH47ZOLA_ART5DIRE_S47-5.60_SCWDIRE"


def test_extracts_all_residential_districts() -> None:
    """Every residential district row in the table becomes a typed standard."""
    rows = extract_dimensional_standards(
        FL_47_5_60_TABLE,
        municipality="Fort Lauderdale",
        county="Broward",
        state="FL",
        source_section_id=FL_SOURCE_SECTION_ID,
        source_url=FL_SOURCE_URL,
    )
    district_codes = {r.district_code for r in rows}
    assert district_codes == {"RS-1", "RS-2", "RS-3", "RS-4", "RM-15"}, (
        f"expected all 5 residential districts, got {district_codes}"
    )


def test_each_row_has_every_numeric_field_populated() -> None:
    """The whole point: typed verified-fact rows with no None values."""
    rows = extract_dimensional_standards(
        FL_47_5_60_TABLE,
        municipality="Fort Lauderdale",
        county="Broward",
        state="FL",
        source_section_id=FL_SOURCE_SECTION_ID,
        source_url=FL_SOURCE_URL,
    )
    rs1 = next(r for r in rows if r.district_code == "RS-1")
    assert rs1.min_lot_area_sqft == 7200.0
    assert rs1.min_lot_width_ft == 50.0
    assert rs1.setback_front_ft == 25.0
    assert rs1.setback_side_ft == 5.0
    assert rs1.setback_rear_ft == 25.0
    assert rs1.max_height_ft == 35.0
    assert rs1.max_lot_coverage_pct == 40.0
    assert rs1.far == 0.50
    assert rs1.max_density_units_per_acre == 6.0


def test_each_row_carries_provenance() -> None:
    """No verified-fact claim without evidence — provenance is mandatory."""
    rows = extract_dimensional_standards(
        FL_47_5_60_TABLE,
        municipality="Fort Lauderdale",
        county="Broward",
        state="FL",
        source_section_id=FL_SOURCE_SECTION_ID,
        source_url=FL_SOURCE_URL,
    )
    for r in rows:
        assert r.source_section_id == FL_SOURCE_SECTION_ID
        assert r.source_url == FL_SOURCE_URL
        assert r.municipality == "Fort Lauderdale"
        assert r.county == "Broward"
        assert r.state == "FL"
        assert r.extracted_at is not None


def test_round_trip_to_numeric_zoning_params() -> None:
    """The calculator must be able to consume a typed row as if it were
    NumericZoningParams — this is the verified-fact path that replaces
    LLM extraction at query time."""
    rows = extract_dimensional_standards(
        FL_47_5_60_TABLE,
        municipality="Fort Lauderdale",
        county="Broward",
        state="FL",
        source_section_id=FL_SOURCE_SECTION_ID,
        source_url=FL_SOURCE_URL,
    )
    rs1 = next(r for r in rows if r.district_code == "RS-1")
    params = rs1.to_numeric_zoning_params()
    assert params.max_density_units_per_acre == 6.0
    assert params.far == 0.50
    assert params.max_lot_coverage_pct == 40.0
    assert params.max_height_ft == 35.0
