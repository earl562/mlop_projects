"""Tests for the hybrid address lookup pipeline."""

import json

import pytest
from unittest.mock import AsyncMock, patch

from plotlot.core.types import PropertyRecord, SearchResult, ZoningReport
from plotlot.pipeline.lookup import (
    _build_context_message,
    _build_report,
    _build_fallback_report,
    lookup_address,
    report_to_dict,
)


def _make_geo(**kwargs):
    defaults = {
        "formatted_address": "7940 Plantation Blvd, Miramar, FL 33023",
        "municipality": "Miramar",
        "county": "Broward",
        "lat": 25.977,
        "lng": -80.232,
    }
    defaults.update(kwargs)
    return defaults


def _make_prop(**kwargs):
    defaults = {
        "folio": "504210230010",
        "address": "7940 PLANTATION BLVD",
        "zoning_code": "RS-4",
        "lot_size_sqft": 8000.0,
        "bedrooms": 4,
        "bathrooms": 3.0,
        "year_built": 2005,
    }
    defaults.update(kwargs)
    return PropertyRecord(**defaults)


def _make_result(**kwargs):
    defaults = {
        "section": "Sec. 500",
        "section_title": "Permitted Uses",
        "zone_codes": ["RS-4"],
        "chunk_text": "Single-family residential district.",
        "score": 0.85,
        "municipality": "Miramar",
    }
    defaults.update(kwargs)
    return SearchResult(**defaults)


class TestBuildContextMessage:
    def test_includes_all_sections(self):
        msg = _build_context_message("123 Main St", _make_geo(), _make_prop(), [_make_result()])
        assert "Geocoding Result" in msg
        assert "Property Record" in msg
        assert "Zoning Ordinance" in msg
        assert "RS-4" in msg
        assert "504210230010" in msg

    def test_no_property_record(self):
        msg = _build_context_message("123 Main St", _make_geo(), None, [])
        assert "Not found in county records" in msg

    def test_no_search_results(self):
        msg = _build_context_message("123 Main St", _make_geo(), _make_prop(), [])
        assert "No matching sections found" in msg


class TestBuildReport:
    def test_from_submission(self):
        args = {
            "zoning_district": "RS-4",
            "summary": "Residential district",
            "confidence": "high",
            "setbacks_front": "25 ft",
        }
        report = _build_report(args, "123 Main St", _make_geo(), _make_prop(), ["Sec. 500"])
        assert isinstance(report, ZoningReport)
        assert report.zoning_district == "RS-4"
        assert report.setbacks.front == "25 ft"
        assert report.property_record.folio == "504210230010"

    def test_fallback(self):
        report = _build_fallback_report("123 Main St", _make_geo(), _make_prop(), ["Sec. 500"])
        assert report.zoning_district == "RS-4"
        assert report.confidence == "low"

    def test_fallback_no_property(self):
        report = _build_fallback_report("123 Main St", _make_geo(), None, [])
        assert report.zoning_district == ""


class TestReportToDict:
    def test_full_report(self):
        """report_to_dict serializes a complete ZoningReport."""
        from plotlot.core.types import DensityAnalysis, NumericZoningParams
        args = {
            "zoning_district": "RS-4",
            "summary": "Residential district",
            "confidence": "high",
            "max_density_units_per_acre": 6.0,
            "setback_front_ft": 25.0,
        }
        report = _build_report(args, "123 Main St", _make_geo(), _make_prop(), ["Sec. 500"])
        d = report_to_dict(report)
        assert d["zoning_district"] == "RS-4"
        assert d["municipality"] == "Miramar"
        assert d["confidence"] == "high"
        assert d["numeric_params"]["max_density_units_per_acre"] == 6.0
        assert d["property_record"]["folio"] == "504210230010"
        assert d["sources"] == ["Sec. 500"]

    def test_minimal_report(self):
        """report_to_dict handles report with no numeric params or density."""
        report = _build_fallback_report("123 Main St", _make_geo(), None, [])
        d = report_to_dict(report)
        assert d["numeric_params"] == {}
        assert d["density_analysis"] is None
        assert d["property_record"] is None


class TestLookupAddress:
    @pytest.mark.asyncio
    async def test_geocode_failure(self):
        with patch("plotlot.pipeline.lookup.geocode_address", return_value=None):
            result = await lookup_address("bad address")
        assert result is None

    @pytest.mark.asyncio
    async def test_full_pipeline_with_submit(self):
        """LLM calls submit_report on first turn."""
        mock_session = AsyncMock()

        async def mock_call_llm(messages, tools=None):
            return {
                "content": "",
                "tool_calls": [{
                    "id": "call_1",
                    "function": {
                        "name": "submit_report",
                        "arguments": json.dumps({
                            "zoning_district": "RS-4",
                            "zoning_description": "Single Family Residential",
                            "summary": "Residential district allowing single-family homes.",
                            "confidence": "high",
                        }),
                    },
                }],
            }

        with patch("plotlot.pipeline.lookup.geocode_address", return_value=_make_geo()), \
             patch("plotlot.pipeline.lookup.lookup_property", return_value=_make_prop()), \
             patch("plotlot.pipeline.lookup.hybrid_search", return_value=[_make_result()]), \
             patch("plotlot.pipeline.lookup.get_session", return_value=mock_session), \
             patch("plotlot.retrieval.llm.call_llm", side_effect=mock_call_llm):
            result = await lookup_address("7940 Plantation Blvd, Miramar, FL")

        assert isinstance(result, ZoningReport)
        assert result.zoning_district == "RS-4"
        assert result.confidence == "high"
        assert result.property_record is not None

    @pytest.mark.asyncio
    async def test_llm_returns_json_directly(self):
        """LLM returns JSON as text instead of calling submit_report."""
        mock_session = AsyncMock()

        async def mock_call_llm(messages, tools=None):
            return {
                "content": json.dumps({
                    "zoning_district": "R-1",
                    "summary": "Single family zone",
                    "confidence": "medium",
                }),
                "tool_calls": [],
            }

        with patch("plotlot.pipeline.lookup.geocode_address", return_value=_make_geo()), \
             patch("plotlot.pipeline.lookup.lookup_property", return_value=_make_prop()), \
             patch("plotlot.pipeline.lookup.hybrid_search", return_value=[_make_result()]), \
             patch("plotlot.pipeline.lookup.get_session", return_value=mock_session), \
             patch("plotlot.retrieval.llm.call_llm", side_effect=mock_call_llm):
            result = await lookup_address("171 NE 209th Ter, Miami, FL")

        assert isinstance(result, ZoningReport)
        assert result.zoning_district == "R-1"

    @pytest.mark.asyncio
    async def test_llm_failure_returns_fallback(self):
        mock_session = AsyncMock()

        with patch("plotlot.pipeline.lookup.geocode_address", return_value=_make_geo()), \
             patch("plotlot.pipeline.lookup.lookup_property", return_value=_make_prop()), \
             patch("plotlot.pipeline.lookup.hybrid_search", return_value=[_make_result()]), \
             patch("plotlot.pipeline.lookup.get_session", return_value=mock_session), \
             patch("plotlot.retrieval.llm.call_llm", return_value=None):
            result = await lookup_address("7940 Plantation Blvd, Miramar, FL")

        assert isinstance(result, ZoningReport)
        assert result.confidence == "low"
        assert result.property_record is not None
