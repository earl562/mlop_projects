"""WIRE-1.1b contract tests: lookup.py consumes the typed dimensional standard.

These pin the lookup-side wiring (criteria 2, 3, 7) — the calculator-side
contract is in test_calculator.py::TestDistrictDimensionalStandardWiring.

  * A storage/query function ``get_dimensional_standard(municipality, district_code)``
    returns a stored DistrictDimensionalStandard or None (criterion 2).
  * lookup.py calls the storage function before LLM extraction; when a standard
    is available, calculate_max_units receives the typed standard instead of
    report.numeric_params (criterion 3).
  * Contract test: with a standard present, calculate_max_units receives a
    DistrictDimensionalStandard; without, the LLM-extracted NumericZoningParams
    path runs (criterion 7).
"""

from __future__ import annotations

import json
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

import pytest

from plotlot.core.types import CoastalHeightOverlay, NumericZoningParams, PropertyRecord
from plotlot.domain.dimensional_standard import DistrictDimensionalStandard
from plotlot.pipeline.calculator import calculate_max_units
from plotlot.pipeline.lookup import lookup_address
from plotlot.storage import dimensional_standards as ds_store


# ── Storage/query function contract (criterion 2) ─────────────────────────────


class TestDimensionalStandardStore:
    def test_returns_stored_standard_for_municipality_and_district(self):
        # The seeded Fort Lauderdale fixture is the reference municipality.
        standard = ds_store.get_dimensional_standard_from_fixture("Fort Lauderdale", "RS-8")
        assert isinstance(standard, DistrictDimensionalStandard)
        assert standard.district_code == "RS-8"
        assert standard.municipality == "Fort Lauderdale"
        assert standard.max_density_units_per_acre == 8.0
        assert standard.source_section_id  # provenance populated

    def test_returns_none_on_miss(self):
        assert ds_store.get_dimensional_standard_from_fixture("Nowhere", "ZZ-9") is None
        assert ds_store.get_dimensional_standard_from_fixture("Fort Lauderdale", "ZZ-9") is None

    def test_returns_none_on_empty_inputs(self):
        assert ds_store.get_dimensional_standard_from_fixture("", "RS-8") is None
        assert ds_store.get_dimensional_standard_from_fixture("Fort Lauderdale", "") is None

    def test_matching_is_case_insensitive(self):
        a = ds_store.get_dimensional_standard_from_fixture("fort lauderdale", "rs-8")
        b = ds_store.get_dimensional_standard_from_fixture("FORT LAUDERDALE", "RS-8")
        assert a is not None and b is not None
        assert a.district_code == "RS-8" == b.district_code

    def test_register_then_lookup_round_trip(self):
        custom = DistrictDimensionalStandard(
            municipality="Testburg",
            county="Test County",
            state="FL",
            district_code="RM-30",
            max_density_units_per_acre=30.0,
        )
        ds_store.register_dimensional_standard_fixture(custom)
        got = ds_store.get_dimensional_standard_from_fixture("Testburg", "RM-30")
        assert got is custom

    @pytest.mark.asyncio
    async def test_async_get_falls_back_to_fixture_without_db(self):
        # get_dimensional_standard tries the DB first; with no DB reachable it
        # falls back to the fixture store. The contract: same return type as the
        # fixture lookup, None on miss.
        standard = await ds_store.get_dimensional_standard("Fort Lauderdale", "RS-8")
        assert isinstance(standard, DistrictDimensionalStandard)
        assert standard.district_code == "RS-8"
        miss = await ds_store.get_dimensional_standard("Nowhere", "ZZ-9")
        assert miss is None


# ── lookup.py wiring (criteria 3 + 7) ─────────────────────────────────────────


def _ftl_geo():
    return {
        "formatted_address": "101 SE 1st Ave, Fort Lauderdale, FL 33301",
        "municipality": "Fort Lauderdale",
        "county": "Broward",
        "state": "FL",
        "lat": 26.113,
        "lng": -80.144,
        "accuracy": 0.95,
    }


def _ftl_prop():
    r = PropertyRecord(county="Broward")
    r.municipality = "Fort Lauderdale"
    r.zoning_code = "RS-8"
    r.lot_size_sqft = 43560.0  # 1 acre → 8 units at 8 du/ac
    r.lot_dimensions = "100x435"
    r.lat = 26.113
    r.lng = -80.144
    return r


def _submit_report_llm(district: str = "RS-8"):
    """An LLM that immediately calls submit_report with residential numeric params."""

    async def _mock(messages, tools=None):
        return {
            "content": "",
            "tool_calls": [
                {
                    "id": "call_1",
                    "function": {
                        "name": "submit_report",
                        "arguments": json.dumps(
                            {
                                "zoning_district": district,
                                "zoning_description": "Single Family Residential",
                                "summary": "RS-8 single-family district.",
                                "confidence": "high",
                                "max_density_units_per_acre": 8.0,
                                "setback_front_ft": 25.0,
                                "property_type": "single_family",
                            }
                        ),
                    },
                }
            ],
        }

    return _mock


def _enter_lookup_patches(stack, *, get_std_return, calc_side_effect=None):
    """Enter the standard lookup-pipeline patches onto ``stack`` (ExitStack).

    Mirrors tests/unit/test_lookup.py::TestLookupAddress (light patching — the
    global conftest disables MLflow tracing, so the tracing decorators no-op).
    The coastal overlay is mocked because it would otherwise make a live network
    call; Fort Lauderdale is outside San Diego so it returns not_applicable.

    Returns ``(mock_get_std, mock_calc)`` so tests can assert on call args / the
    params the calculator received.
    """
    from plotlot.pipeline import lookup as lookup_mod

    stack.enter_context(patch("plotlot.pipeline.lookup.geocode_address", return_value=_ftl_geo()))
    stack.enter_context(patch("plotlot.pipeline.lookup.lookup_property", return_value=_ftl_prop()))
    stack.enter_context(patch("plotlot.pipeline.lookup.hybrid_search", return_value=[]))
    stack.enter_context(patch("plotlot.pipeline.lookup.get_session", return_value=AsyncMock()))
    stack.enter_context(patch("plotlot.retrieval.llm.call_llm", side_effect=_submit_report_llm()))
    stack.enter_context(
        patch(
            "plotlot.pipeline.coastal_overlay.fetch_coastal_height_overlay",
            new_callable=AsyncMock,
            return_value=CoastalHeightOverlay(status="not_applicable"),
        )
    )
    mock_get_std = stack.enter_context(
        patch.object(
            lookup_mod,
            "get_dimensional_standard",
            new_callable=AsyncMock,
            return_value=get_std_return,
        )
    )
    mock_calc = None
    if calc_side_effect is not None:
        mock_calc = stack.enter_context(
            patch("plotlot.pipeline.lookup.calculate_max_units", side_effect=calc_side_effect)
        )
    return mock_get_std, mock_calc


@pytest.mark.asyncio
async def test_lookup_uses_typed_standard_when_present():
    """With a stored standard, calculate_max_units receives a typed
    DistrictDimensionalStandard — the verified-fact path (criterion 3)."""
    from plotlot.pipeline import lookup as lookup_mod

    lookup_mod._pipeline_cache.clear()

    captured = {}

    def _spy_calc(*args, **kwargs):
        captured["params"] = kwargs.get("params", args[1] if len(args) > 1 else None)
        captured["density_verified"] = kwargs.get("density_verified", False)
        captured["min_lot_area_verified"] = kwargs.get("min_lot_area_verified", False)
        # Delegate to the real calculator so the DensityAnalysis is real.
        return calculate_max_units(*args, **kwargs)

    standard = ds_store.get_dimensional_standard_from_fixture("Fort Lauderdale", "RS-8")
    with ExitStack() as stack:
        mock_get_std, _ = _enter_lookup_patches(
            stack, get_std_return=standard, calc_side_effect=_spy_calc
        )
        report = await lookup_address("101 SE 1st Ave, Fort Lauderdale, FL 33301")

    assert report is not None
    assert report.density_analysis is not None
    # The typed standard was looked up for the parcel's district.
    mock_get_std.assert_awaited()
    called_args = mock_get_std.call_args.args
    assert called_args[0] == "Fort Lauderdale"
    assert "RS-8" in called_args[1]
    # calculate_max_units received the typed standard, NOT the LLM NumericZoningParams.
    assert isinstance(captured["params"], DistrictDimensionalStandard)
    # The typed row is the authority → provenance label is verified-fact grade.
    # (density_verified/min_lot_area_verified are calculator-internal locals, not
    # DensityAnalysis fields; the observable contract is origin=local_authority,
    # asserted below, plus max_units.)
    # Provenance label: verified-fact grade, not assumption-grade LLM extraction.
    assert report.density_analysis.origin == "local_authority"
    assert report.density_analysis.max_units == 8  # 8 du/ac × 1 acre


@pytest.mark.asyncio
async def test_lookup_falls_back_to_llm_params_when_no_standard():
    """Without a stored standard, the LLM-extracted NumericZoningParams path runs
    (criterion 7, the 'without' case) and the result is assumption-grade."""
    from plotlot.pipeline import lookup as lookup_mod

    lookup_mod._pipeline_cache.clear()

    captured = {}

    def _spy_calc(*args, **kwargs):
        captured["params"] = kwargs.get("params", args[1] if len(args) > 1 else None)
        return calculate_max_units(*args, **kwargs)

    with ExitStack() as stack:
        mock_get_std, _ = _enter_lookup_patches(
            stack, get_std_return=None, calc_side_effect=_spy_calc
        )
        report = await lookup_address("200 SW 2nd Ave, Fort Lauderdale, FL 33301")

    assert report is not None
    assert report.density_analysis is not None
    mock_get_std.assert_awaited()
    # No standard → the LLM-extracted NumericZoningParams fed the calculator.
    assert isinstance(captured["params"], NumericZoningParams)
    assert not isinstance(captured["params"], DistrictDimensionalStandard)
    # Assumption-grade provenance label.
    assert report.density_analysis.origin == "unknown"
    assert report.density_analysis.max_units == 8


@pytest.mark.asyncio
async def test_typed_standard_takes_precedence_over_llm_numeric_params():
    """When BOTH a typed standard and LLM-extracted numeric_params exist, the
    typed standard governs the density calculation (origin=local_authority)."""
    from plotlot.pipeline import lookup as lookup_mod

    lookup_mod._pipeline_cache.clear()

    standard = ds_store.get_dimensional_standard_from_fixture("Fort Lauderdale", "RS-8")
    with ExitStack() as stack:
        _enter_lookup_patches(stack, get_std_return=standard)
        report = await lookup_address("303 NE 3rd Ave, Fort Lauderdale, FL 33301")

    assert report.density_analysis is not None
    # The LLM did produce numeric_params (assumption-grade)…
    assert report.numeric_params is not None
    assert report.numeric_params.max_density_units_per_acre == 8.0
    # …but the density analysis is labeled verified-fact (the typed row governed).
    assert report.density_analysis.origin == "local_authority"


@pytest.mark.asyncio
async def test_lookup_queries_parcel_district_code():
    """The storage query is keyed on the parcel's district code (the crosswalked
    ordinance code when matched, else the GIS zone code), so the right typed row
    is read out of a multi-district dimensional table."""
    from plotlot.pipeline import lookup as lookup_mod

    lookup_mod._pipeline_cache.clear()

    with ExitStack() as stack:
        mock_get_std, _ = _enter_lookup_patches(stack, get_std_return=None)
        await lookup_address("404 NW 4th Ave, Fort Lauderdale, FL 33301")

    # No Fort Lauderdale crosswalk exists, so the GIS code "RS-8" is queried
    # directly (the fall-through when crosswalk.matched is False).
    queried_codes = [call.args[1] for call in mock_get_std.call_args_list]
    assert "RS-8" in queried_codes
    # And the municipality is the resolved one.
    assert all(call.args[0] == "Fort Lauderdale" for call in mock_get_std.call_args_list)
