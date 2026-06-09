"""Regression test for the indexed-municipality zoning retrieval bug.

Bug: When ArcGIS doesn't return a zoning code (e.g. Santa Clara County), the
search_query fell back to the municipality name (e.g. "San Jose").  That name has
no semantic overlap with ordinance text, so hybrid_search returned 0 results even
though 1,409 chunks were indexed.  The LLM then hallucinated "zoning not accessible."

Fix: Fall back to a generic zoning-terms query instead of the municipality name.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from plotlot.core.types import PropertyRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_GENERIC_ZONING_TERMS = "zoning district residential density setbacks height limits parking"


def _prop_record_no_zoning_code() -> PropertyRecord:
    """Simulate a PropertyRecord where ArcGIS returned no zoning code."""
    r = PropertyRecord(county="Santa Clara")
    r.municipality = "San Jose"
    r.zoning_code = ""  # ArcGIS Santa Clara doesn't populate this
    r.lot_size_sqft = 7500.0
    r.lat = 37.3382
    r.lng = -121.8863
    return r


def _prop_record_with_zoning_code() -> PropertyRecord:
    """Simulate a PropertyRecord where ArcGIS did return a zoning code."""
    r = PropertyRecord(county="Miami-Dade")
    r.municipality = "Miami Gardens"
    r.zoning_code = "RS-1"
    r.lot_size_sqft = 6000.0
    r.lat = 25.9420
    r.lng = -80.2456
    return r


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


def test_search_query_uses_zoning_code_when_present() -> None:
    """When a zoning code is available, it should be used as the search query."""
    prop = _prop_record_with_zoning_code()
    search_query = prop.zoning_code if prop and prop.zoning_code else _GENERIC_ZONING_TERMS
    assert search_query == "RS-1"


def test_search_query_falls_back_to_generic_terms_not_municipality_name() -> None:
    """When no zoning code, query must NOT be the municipality name."""
    prop = _prop_record_no_zoning_code()
    search_query = prop.zoning_code if prop and prop.zoning_code else _GENERIC_ZONING_TERMS
    assert search_query != "San Jose", (
        "Regression: municipality name as query returns 0 results from hybrid_search"
    )
    assert search_query == _GENERIC_ZONING_TERMS


def test_search_query_falls_back_when_prop_record_is_none() -> None:
    """When the entire PropertyRecord is None, still use generic terms."""
    prop = None
    search_query = (
        prop.zoning_code  # type: ignore[union-attr]
        if prop and prop.zoning_code
        else _GENERIC_ZONING_TERMS
    )
    assert search_query == _GENERIC_ZONING_TERMS


def test_search_query_generic_terms_contain_zoning_keywords() -> None:
    """The generic fallback must include terms that match zoning ordinance text."""
    keywords = ["zoning", "district", "residential", "density", "setbacks"]
    for kw in keywords:
        assert kw in _GENERIC_ZONING_TERMS, f"Generic fallback missing keyword: {kw!r}"


# ---------------------------------------------------------------------------
# Integration-style: verify lookup.py uses the correct fallback
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lookup_uses_generic_query_not_municipality_when_no_zoning_code() -> None:
    """End-to-end regression: hybrid_search must NOT be called with municipality name."""
    fake_chunk = MagicMock()
    fake_chunk.section = "21.100"
    fake_chunk.section_title = "Residential Districts"
    fake_chunk.chapter = "21"
    fake_chunk.zone_codes = ["R-1"]
    fake_chunk.score = 0.85
    fake_chunk.chunk_text = "The R-1 zoning district allows single-family residential uses."
    fake_chunk.source_url = "https://library.municode.com/ca/san_jose"

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
            "lat": 37.3382,
            "lng": -121.8863,
            "county": "Santa Clara",
            "municipality": "San Jose",
            "state": "CA",
            "formatted_address": "100 Main St, San Jose, CA 95101",
        }

        prop = _prop_record_no_zoning_code()
        mock_prop.return_value = prop  # AsyncMock — awaiting returns prop

        mock_report = MagicMock()
        mock_report.numeric_params = None
        mock_analysis.return_value = mock_report

        from plotlot.pipeline.lookup import lookup_address

        await lookup_address("100 Main St, San Jose, CA 95101")

        # Verify hybrid_search was NOT called with "San Jose" as the query
        calls = mock_search.call_args_list
        assert calls, "hybrid_search was never called"
        for call in calls:
            query_arg = call.args[2] if len(call.args) > 2 else call.kwargs.get("query", "")
            assert query_arg != "San Jose", (
                f"Regression: hybrid_search called with municipality name {query_arg!r} "
                "instead of generic zoning terms"
            )
            assert "zoning" in query_arg.lower(), (
                f"Expected generic zoning terms in query, got: {query_arg!r}"
            )
