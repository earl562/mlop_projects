"""Integration test: the lookup pipeline crosswalks the GIS code before search.

Regression context (§8.3c): the GIS layer reports "RS20" for the Las Vegas test
parcel, but Clark County Title 30 only ever uses "R-E". Searching the ordinance
for "RS20" matches nothing even after Clark County is ingested. The pipeline now
translates the GIS code to the ordinance code BEFORE the hybrid search and uses
it as the exact-code boost, so the ingested text actually matches.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from plotlot.core.types import PropertyRecord


def _clark_rs20_record() -> PropertyRecord:
    """Unincorporated Clark County parcel as the provider now labels it."""
    r = PropertyRecord(county="Clark")
    r.municipality = "Clark County"  # provider (a): labeled by the county layer
    r.zoning_code = "RS20"  # GIS map label
    r.lot_size_sqft = 23522.0
    r.lat = 36.1352
    r.lng = -115.2483
    return r


@pytest.mark.asyncio
async def test_lookup_searches_ordinance_code_not_gis_code() -> None:
    """hybrid_search must be called with 'R-E' (ordinance), not 'RS20' (GIS)."""
    fake_chunk = MagicMock()
    fake_chunk.section = "30.40"
    fake_chunk.section_title = "Rural Residential Districts"
    fake_chunk.chapter = "30"
    fake_chunk.zone_codes = ["R-E"]
    fake_chunk.score = 0.9
    fake_chunk.chunk_text = "The R-E rural estates district requires a 20,000 sqft minimum lot."
    fake_chunk.source_url = "https://library.municode.com/nv/clark_county"

    fake_session = AsyncMock()
    fake_session.close = AsyncMock()

    with (
        patch("plotlot.pipeline.lookup.geocode_address", new_callable=AsyncMock) as mock_geocode,
        patch("plotlot.pipeline.lookup.lookup_property", new_callable=AsyncMock) as mock_prop,
        patch(
            "plotlot.pipeline.lookup.get_session", new_callable=AsyncMock, return_value=fake_session
        ),
        patch(
            "plotlot.pipeline.lookup.hybrid_search",
            new_callable=AsyncMock,
            return_value=[fake_chunk],
        ) as mock_search,
        patch("plotlot.pipeline.lookup._agentic_analysis", new_callable=AsyncMock) as mock_analysis,
        patch("plotlot.pipeline.lookup.log_params"),
        patch("plotlot.pipeline.lookup.start_run"),
        patch("plotlot.pipeline.lookup.log_metrics"),
        patch("plotlot.pipeline.lookup.set_tag"),
        patch("plotlot.pipeline.lookup.log_dict"),
        patch("plotlot.pipeline.lookup.start_span"),
        patch("plotlot.pipeline.lookup.trace"),
        patch("plotlot.pipeline.lookup.log_prompt_to_run"),
        patch("plotlot.pipeline.lookup.get_active_prompt", return_value=""),
    ):
        mock_geocode.return_value = {
            "lat": 36.1352,
            "lng": -115.2483,
            "county": "Clark",
            "municipality": "Las Vegas",  # mailing city — overridden by the record
            "state": "NV",
            "formatted_address": "2975 Montessouri St, Las Vegas, NV 89117",
        }
        mock_prop.return_value = _clark_rs20_record()

        mock_report = MagicMock()
        mock_report.numeric_params = None
        mock_analysis.return_value = mock_report

        from plotlot.pipeline.lookup import lookup_address

        await lookup_address("2975 Montessouri St, Las Vegas, NV 89117")

    calls = mock_search.call_args_list
    assert calls, "hybrid_search was never called"
    call = calls[0]
    query_arg = call.args[2] if len(call.args) > 2 else call.kwargs.get("zone_code", "")
    assert query_arg == "R-E", f"expected ordinance code 'R-E' as query, got {query_arg!r}"
    assert call.kwargs.get("zone_code_boost") == "R-E", (
        "expected exact-code boost on the ordinance code"
    )

    # The agent must be told to report standards under the ordinance code.
    analysis_kwargs = mock_analysis.call_args.kwargs
    assert analysis_kwargs.get("ordinance_code") == "R-E"


@pytest.mark.asyncio
async def test_lookup_passes_gis_code_through_when_no_crosswalk() -> None:
    """A jurisdiction without a crosswalk entry searches the GIS code unchanged."""
    fake_chunk = MagicMock()
    fake_chunk.section = "21.100"
    fake_chunk.section_title = "Residential"
    fake_chunk.chapter = "21"
    fake_chunk.zone_codes = ["RS-1"]
    fake_chunk.score = 0.85
    fake_chunk.chunk_text = "RS-1 single-family district."
    fake_chunk.source_url = ""

    fake_session = AsyncMock()
    fake_session.close = AsyncMock()

    record = PropertyRecord(county="Miami-Dade")
    record.municipality = "Miami Gardens"
    record.zoning_code = "RS-1"
    record.lot_size_sqft = 6000.0
    record.lat = 25.942
    record.lng = -80.2456

    with (
        patch("plotlot.pipeline.lookup.geocode_address", new_callable=AsyncMock) as mock_geocode,
        patch("plotlot.pipeline.lookup.lookup_property", new_callable=AsyncMock) as mock_prop,
        patch(
            "plotlot.pipeline.lookup.get_session", new_callable=AsyncMock, return_value=fake_session
        ),
        patch(
            "plotlot.pipeline.lookup.hybrid_search",
            new_callable=AsyncMock,
            return_value=[fake_chunk],
        ) as mock_search,
        patch("plotlot.pipeline.lookup._agentic_analysis", new_callable=AsyncMock) as mock_analysis,
        patch("plotlot.pipeline.lookup.log_params"),
        patch("plotlot.pipeline.lookup.start_run"),
        patch("plotlot.pipeline.lookup.log_metrics"),
        patch("plotlot.pipeline.lookup.set_tag"),
        patch("plotlot.pipeline.lookup.log_dict"),
        patch("plotlot.pipeline.lookup.start_span"),
        patch("plotlot.pipeline.lookup.trace"),
        patch("plotlot.pipeline.lookup.log_prompt_to_run"),
        patch("plotlot.pipeline.lookup.get_active_prompt", return_value=""),
    ):
        mock_geocode.return_value = {
            "lat": 25.942,
            "lng": -80.2456,
            "county": "Miami-Dade",
            "municipality": "Miami Gardens",
            "state": "FL",
            "formatted_address": "123 Main St, Miami Gardens, FL",
        }
        mock_prop.return_value = record

        mock_report = MagicMock()
        mock_report.numeric_params = None
        mock_analysis.return_value = mock_report

        from plotlot.pipeline.lookup import lookup_address

        await lookup_address("123 Main St, Miami Gardens, FL")

    call = mock_search.call_args_list[0]
    query_arg = call.args[2] if len(call.args) > 2 else call.kwargs.get("zone_code", "")
    assert query_arg == "RS-1", f"unmapped code should pass through, got {query_arg!r}"
    assert call.kwargs.get("zone_code_boost") == "RS-1"
    # No crosswalk → no ordinance-code hint forced on the agent.
    assert mock_analysis.call_args.kwargs.get("ordinance_code") == ""
