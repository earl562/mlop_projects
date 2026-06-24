"""Tests for the hybrid address lookup pipeline."""

import json

import pytest
from unittest.mock import AsyncMock, patch

from plotlot.core.types import (
    ComparableSale,
    CompAnalysis,
    NumericZoningParams,
    PropertyRecord,
    SearchResult,
    ZoningReport,
)
from plotlot.pipeline.lookup import (
    _build_context_message,
    _build_report,
    _build_fallback_report,
    _build_report_from_cache,
    _extract_numeric_params,
    _validate_numeric_params,
    _zone_prefix_defaults,
    clear_zoning_params_cache,
    lookup_address,
    report_to_dict,
)
from plotlot.pipeline.zoning_cache import (
    CachedZoningData,
    _get_cached_zoning_data,
    _get_cached_zoning_params,
    _store_zoning_params,
    _zoning_params_cache_key,
)


@pytest.fixture(autouse=True)
def _isolate_mlflow_tracking(tmp_path):
    """Redirect MLflow tracking to a temp SQLite DB so tests don't hit corrupted mlruns/."""
    import mlflow

    # End any active run leaked from other test modules
    if mlflow.active_run():
        mlflow.end_run()

    prev_uri = mlflow.get_tracking_uri()
    mlflow.set_tracking_uri(f"sqlite:///{tmp_path}/mlflow.db")
    mlflow.set_experiment("test-lookup")
    clear_zoning_params_cache()
    yield
    clear_zoning_params_cache()
    # Clean up any run started during this test
    if mlflow.active_run():
        mlflow.end_run()
    mlflow.set_tracking_uri(prev_uri)


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
    @pytest.mark.asyncio
    async def test_from_submission(self):
        args = {
            "zoning_district": "RS-4",
            "summary": "Residential district",
            "confidence": "high",
            "setbacks_front": "25 ft",
        }
        report = await _build_report(args, "123 Main St", _make_geo(), _make_prop(), ["Sec. 500"])
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

    def test_fallback_salvages_search_result_fields(self):
        result = _make_result(
            zone_codes=["RM-12"],
            chunk_text=(
                "Maximum building height is 35 feet. "
                "Maximum density is 12 dwelling units per acre. "
                "Front setback 25 feet. Side setback 7.5 feet. Rear setback 20 feet. "
                "Maximum lot coverage is 40%. Minimum lot size is 7,500 square feet. "
                "Parking requirement: 2 spaces per unit."
            ),
        )

        report = _build_fallback_report(
            "123 Main St",
            _make_geo(),
            None,
            ["Sec. 500"],
            [result],
        )

        assert report.zoning_district == "RM-12"
        assert report.max_height == "35 ft"
        assert report.max_density == "12 units/acre"
        assert report.setbacks.front == "25 ft"
        assert report.numeric_params is not None
        assert report.numeric_params.max_density_units_per_acre == 12.0
        assert len(report.source_refs) == 1


class TestReportToDict:
    @pytest.mark.asyncio
    async def test_full_report(self):
        """report_to_dict serializes a complete ZoningReport."""
        clear_zoning_params_cache()
        args = {
            "zoning_district": "RS-4",
            "summary": "Residential district",
            "confidence": "high",
            "max_density_units_per_acre": 6.0,
            "setback_front_ft": 25.0,
        }
        report = await _build_report(args, "123 Main St", _make_geo(), _make_prop(), ["Sec. 500"])
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
        with patch(
            "plotlot.pipeline.lookup.geocode_address",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await lookup_address("bad address")
        assert result is None

    @pytest.mark.asyncio
    async def test_full_pipeline_with_submit(self):
        """LLM calls submit_report on first turn."""
        mock_session = AsyncMock()

        async def mock_call_llm(messages, tools=None, temperature=0.1):
            return {
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "submit_report",
                            "arguments": json.dumps(
                                {
                                    "zoning_district": "RS-4",
                                    "zoning_description": "Single Family Residential",
                                    "summary": "Residential district allowing single-family homes.",
                                    "confidence": "high",
                                }
                            ),
                        },
                    }
                ],
            }

        with (
            patch("plotlot.pipeline.lookup.geocode_address", return_value=_make_geo()),
            patch("plotlot.pipeline.lookup.lookup_property", return_value=_make_prop()),
            patch("plotlot.pipeline.lookup.hybrid_search", return_value=[_make_result()]),
            patch("plotlot.pipeline.lookup.get_session", return_value=mock_session),
            patch("plotlot.retrieval.llm.call_llm", side_effect=mock_call_llm),
        ):
            result = await lookup_address("7940 Plantation Blvd, Miramar, FL")

        assert isinstance(result, ZoningReport)
        assert result.zoning_district == "RS-4"
        assert result.confidence == "high"
        assert result.property_record is not None

    @pytest.mark.asyncio
    async def test_llm_returns_json_directly(self):
        """LLM returns JSON as text instead of calling submit_report."""
        mock_session = AsyncMock()

        async def mock_call_llm(messages, tools=None, temperature=0.1):
            return {
                "content": json.dumps(
                    {
                        "zoning_district": "R-1",
                        "summary": "Single family zone",
                        "confidence": "medium",
                    }
                ),
                "tool_calls": [],
            }

        with (
            patch("plotlot.pipeline.lookup.geocode_address", return_value=_make_geo()),
            patch("plotlot.pipeline.lookup.lookup_property", return_value=_make_prop()),
            patch("plotlot.pipeline.lookup.hybrid_search", return_value=[_make_result()]),
            patch("plotlot.pipeline.lookup.get_session", return_value=mock_session),
            patch("plotlot.retrieval.llm.call_llm", side_effect=mock_call_llm),
        ):
            result = await lookup_address("171 NE 209th Ter, Miami, FL")

        assert isinstance(result, ZoningReport)
        assert result.zoning_district == "R-1"

    @pytest.mark.asyncio
    async def test_llm_failure_returns_fallback(self):
        mock_session = AsyncMock()

        # Clear pipeline cache to avoid hits from prior tests
        from plotlot.pipeline.lookup import _pipeline_cache

        _pipeline_cache.clear()

        with (
            patch("plotlot.pipeline.lookup.geocode_address", return_value=_make_geo()),
            patch("plotlot.pipeline.lookup.lookup_property", return_value=_make_prop()),
            patch("plotlot.pipeline.lookup.hybrid_search", return_value=[_make_result()]),
            patch("plotlot.pipeline.lookup.get_session", return_value=mock_session),
            patch("plotlot.retrieval.llm.call_llm", return_value=None),
        ):
            result = await lookup_address("7940 Plantation Blvd, Miramar, FL")

        assert isinstance(result, ZoningReport)
        assert result.confidence == "low"
        assert result.property_record is not None

    @pytest.mark.asyncio
    async def test_none_zoning_code_uses_generic_query(self):
        """PropertyRecord(zoning_code='NONE') treated as no zone code → GENERIC_ZONING_QUERY."""
        from plotlot.pipeline.lookup import GENERIC_ZONING_QUERY, _pipeline_cache

        _pipeline_cache.clear()
        captured_queries: list[str] = []

        async def mock_hybrid_search(session, municipality, query, limit=15, zone_code_boost=None):
            captured_queries.append(query)
            return [_make_result()]

        mock_session = AsyncMock()

        with (
            patch("plotlot.pipeline.lookup.geocode_address", return_value=_make_geo()),
            patch(
                "plotlot.pipeline.lookup.lookup_property",
                return_value=_make_prop(zoning_code="NONE"),
            ),
            patch("plotlot.pipeline.lookup.hybrid_search", side_effect=mock_hybrid_search),
            patch("plotlot.pipeline.lookup.get_session", return_value=mock_session),
            patch("plotlot.retrieval.llm.call_llm", return_value=None),
        ):
            await lookup_address("500 NW 1st Ave, Miami, FL 33127")

        assert captured_queries, "hybrid_search should have been called"
        assert captured_queries[0] == GENERIC_ZONING_QUERY

    @pytest.mark.asyncio
    async def test_empty_zoning_code_uses_generic_query(self):
        """PropertyRecord(zoning_code='') treated as no zone code → GENERIC_ZONING_QUERY."""
        from plotlot.pipeline.lookup import GENERIC_ZONING_QUERY, _pipeline_cache

        _pipeline_cache.clear()
        captured_queries: list[str] = []

        async def mock_hybrid_search(session, municipality, query, limit=15, zone_code_boost=None):
            captured_queries.append(query)
            return [_make_result()]

        mock_session = AsyncMock()

        with (
            patch("plotlot.pipeline.lookup.geocode_address", return_value=_make_geo()),
            patch(
                "plotlot.pipeline.lookup.lookup_property",
                return_value=_make_prop(zoning_code=""),
            ),
            patch("plotlot.pipeline.lookup.hybrid_search", side_effect=mock_hybrid_search),
            patch("plotlot.pipeline.lookup.get_session", return_value=mock_session),
            patch("plotlot.retrieval.llm.call_llm", return_value=None),
        ):
            await lookup_address("600 NW 2nd Ave, Miami, FL 33127")

        assert captured_queries, "hybrid_search should have been called"
        assert captured_queries[0] == GENERIC_ZONING_QUERY

    @pytest.mark.asyncio
    async def test_real_zone_code_uses_zone_in_query(self):
        """PropertyRecord(zoning_code='RS-4') treated as real zone → zone code used in search."""
        from plotlot.pipeline.lookup import _pipeline_cache

        _pipeline_cache.clear()
        captured_queries: list[str] = []

        async def mock_hybrid_search(session, municipality, query, limit=15, zone_code_boost=None):
            captured_queries.append(query)
            return [_make_result()]

        mock_session = AsyncMock()

        with (
            patch("plotlot.pipeline.lookup.geocode_address", return_value=_make_geo()),
            patch(
                "plotlot.pipeline.lookup.lookup_property",
                return_value=_make_prop(zoning_code="RS-4"),
            ),
            patch("plotlot.pipeline.lookup.hybrid_search", side_effect=mock_hybrid_search),
            patch("plotlot.pipeline.lookup.get_session", return_value=mock_session),
            patch("plotlot.retrieval.llm.call_llm", return_value=None),
        ):
            await lookup_address("625 Palm Ave, Miramar, FL 33025")

        assert captured_queries, "hybrid_search should have been called"
        assert captured_queries[0] == "RS-4"

    @pytest.mark.asyncio
    async def test_lookup_address_includes_comps(self):
        """Phase 4: find_comparables() called, result attached to report."""
        from plotlot.pipeline.lookup import _pipeline_cache

        _pipeline_cache.clear()
        mock_session = AsyncMock()

        comp = CompAnalysis(
            comparables=[ComparableSale() for _ in range(5)],
            median_price_per_acre=500000.0,
            estimated_land_value=200000.0,
            confidence=0.9,
        )

        async def mock_find_comparables(subject, **kwargs):
            return comp

        async def mock_call_llm(messages, tools=None, temperature=0.1):
            return {
                "content": json.dumps(
                    {
                        "zoning_district": "RS-4",
                        "summary": "test",
                        "confidence": "high",
                    }
                ),
                "tool_calls": [],
            }

        with (
            patch("plotlot.pipeline.lookup.geocode_address", return_value=_make_geo()),
            patch(
                "plotlot.pipeline.lookup.lookup_property",
                return_value=_make_prop(lat=25.977, lng=-80.232),
            ),
            patch(
                "plotlot.pipeline.lookup.hybrid_search", return_value=[_make_result()]
            ),
            patch("plotlot.pipeline.lookup.get_session", return_value=mock_session),
            patch("plotlot.retrieval.llm.call_llm", side_effect=mock_call_llm),
            patch(
                "plotlot.pipeline.comps.find_comparables",
                side_effect=mock_find_comparables,
            ),
        ):
            result = await lookup_address("7940 Plantation Blvd, Miramar, FL")

        assert result is not None
        assert result.comp_analysis is not None
        assert len(result.comp_analysis.comparables) == 5
        assert result.comp_analysis.confidence == 0.9

    @pytest.mark.asyncio
    async def test_lookup_address_comps_failure_nonblocking(self):
        """Phase 4: comps failure does not crash the pipeline."""
        from plotlot.pipeline.lookup import _pipeline_cache

        _pipeline_cache.clear()
        mock_session = AsyncMock()

        async def mock_find_comparables_error(subject, **kwargs):
            raise RuntimeError("simulated")

        async def mock_call_llm(messages, tools=None, temperature=0.1):
            return {
                "content": json.dumps(
                    {
                        "zoning_district": "RS-4",
                        "summary": "test",
                        "confidence": "high",
                    }
                ),
                "tool_calls": [],
            }

        with (
            patch("plotlot.pipeline.lookup.geocode_address", return_value=_make_geo()),
            patch(
                "plotlot.pipeline.lookup.lookup_property",
                return_value=_make_prop(lat=25.977, lng=-80.232),
            ),
            patch(
                "plotlot.pipeline.lookup.hybrid_search", return_value=[_make_result()]
            ),
            patch("plotlot.pipeline.lookup.get_session", return_value=mock_session),
            patch("plotlot.retrieval.llm.call_llm", side_effect=mock_call_llm),
            patch(
                "plotlot.pipeline.comps.find_comparables",
                side_effect=mock_find_comparables_error,
            ),
        ):
            result = await lookup_address("7940 Plantation Blvd, Miramar, FL")

        assert result is not None
        assert result.confidence == "high"
        assert result.property_record is not None
        assert result.comp_analysis is None


# ── Task 1.3: output pinning tests ──


class TestCacheKeyPinning:
    def test_same_inputs_same_key(self):
        key1 = _zoning_params_cache_key("Broward", "Miramar", "RS-4", ["1", "2", "3"], "gpt-4.1")
        key2 = _zoning_params_cache_key("Broward", "Miramar", "RS-4", ["1", "2", "3"], "gpt-4.1")
        assert key1 == key2

    def test_different_chunk_ids_different_key(self):
        key1 = _zoning_params_cache_key("Broward", "Miramar", "RS-4", ["1", "2"], "gpt-4.1")
        key2 = _zoning_params_cache_key("Broward", "Miramar", "RS-4", ["3", "4"], "gpt-4.1")
        assert key1 != key2

    def test_different_model_different_key(self):
        key1 = _zoning_params_cache_key("Broward", "Miramar", "RS-4", ["1", "2"], "gpt-4.1")
        key2 = _zoning_params_cache_key("Broward", "Miramar", "RS-4", ["1", "2"], "gpt-4o")
        assert key1 != key2

    def test_chunk_order_normalized(self):
        key1 = _zoning_params_cache_key("Broward", "Miramar", "RS-4", ["3", "1", "2"], "gpt-4.1")
        key2 = _zoning_params_cache_key("Broward", "Miramar", "RS-4", ["1", "2", "3"], "gpt-4.1")
        assert key1 == key2

    def test_case_and_whitespace_normalized(self):
        key1 = _zoning_params_cache_key(" broward ", " MIRAMAR ", " rs-4 ", ["1"], "gpt-4.1")
        key2 = _zoning_params_cache_key("Broward", "Miramar", "RS-4", ["1"], "gpt-4.1")
        assert key1 == key2

    @pytest.mark.asyncio
    async def test_same_zone_different_chunks_cache_miss(self):
        clear_zoning_params_cache()
        params = NumericZoningParams(max_density_units_per_acre=6.0)
        data = CachedZoningData(numeric_params=params, confidence="high", summary="test")
        await _store_zoning_params(
            "Broward", "Miramar", "RS-4", data, chunk_ids=["1", "2"], model_id="gpt-4.1"
        )

        result = _get_cached_zoning_data(
            "Broward", "Miramar", "RS-4", chunk_ids=["3", "4"], model_id="gpt-4.1"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_same_zone_same_chunks_cache_hit(self):
        clear_zoning_params_cache()
        params = NumericZoningParams(max_density_units_per_acre=6.0)
        data = CachedZoningData(numeric_params=params, confidence="high", summary="test")
        await _store_zoning_params(
            "Broward", "Miramar", "RS-4", data, chunk_ids=["1", "2"], model_id="gpt-4.1"
        )

        result = _get_cached_zoning_data(
            "Broward", "Miramar", "RS-4", chunk_ids=["1", "2"], model_id="gpt-4.1"
        )
        assert result is not None
        assert result.numeric_params.max_density_units_per_acre == 6.0
        assert result.confidence == "high"

    @pytest.mark.asyncio
    async def test_same_zone_same_chunks_different_model_cache_miss(self):
        clear_zoning_params_cache()
        params = NumericZoningParams(max_density_units_per_acre=6.0)
        data = CachedZoningData(numeric_params=params, confidence="high", summary="test")
        await _store_zoning_params(
            "Broward", "Miramar", "RS-4", data, chunk_ids=["1", "2"], model_id="gpt-4.1"
        )

        result = _get_cached_zoning_data(
            "Broward", "Miramar", "RS-4", chunk_ids=["1", "2"], model_id="gpt-4o"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_backward_compat_lookup_without_chunk_ids(self):
        clear_zoning_params_cache()
        params = NumericZoningParams(max_density_units_per_acre=8.0)
        data = CachedZoningData(numeric_params=params, confidence="medium", summary="compat")
        await _store_zoning_params(
            "Broward", "Miramar", "RS-4", data, chunk_ids=["10", "20"], model_id="gpt-4.1"
        )

        result = _get_cached_zoning_params("Broward", "Miramar", "RS-4")
        assert result is not None
        assert result.max_density_units_per_acre == 8.0


# ── Task 1.4: cache text storage tests ──


class TestCacheTextStorage:
    @pytest.mark.asyncio
    async def test_cached_data_round_trip(self):
        clear_zoning_params_cache()
        params = NumericZoningParams(
            max_density_units_per_acre=12.0,
            max_height_ft=35.0,
            setback_front_ft=25.0,
        )
        data = CachedZoningData(
            numeric_params=params,
            zoning_description="Multi-Family Residential District",
            allowed_uses=["apartments", "townhouses"],
            conditional_uses=["daycare"],
            prohibited_uses=["industrial", "warehouse"],
            summary="Medium-density residential zoning allowing up to 12 units/acre.",
            confidence="high",
        )
        await _store_zoning_params(
            "Broward", "Miramar", "RM-12", data, chunk_ids=["100", "200"], model_id="gpt-4.1"
        )

        retrieved = _get_cached_zoning_data(
            "Broward", "Miramar", "RM-12", chunk_ids=["100", "200"], model_id="gpt-4.1"
        )
        assert retrieved is not None
        assert retrieved.zoning_description == "Multi-Family Residential District"
        assert retrieved.allowed_uses == ["apartments", "townhouses"]
        assert retrieved.conditional_uses == ["daycare"]
        assert retrieved.prohibited_uses == ["industrial", "warehouse"]
        assert (
            retrieved.summary == "Medium-density residential zoning allowing up to 12 units/acre."
        )
        assert retrieved.confidence == "high"
        assert retrieved.extracted_at, "extracted_at should be set automatically"
        assert retrieved.numeric_params.max_density_units_per_acre == 12.0

    def test_build_report_from_cache_uses_stored_text(self):
        clear_zoning_params_cache()
        params = NumericZoningParams(
            max_density_units_per_acre=12.0,
            max_height_ft=35.0,
        )
        cached_data = CachedZoningData(
            numeric_params=params,
            zoning_description="Stored LLM description",
            allowed_uses=["use-a", "use-b"],
            conditional_uses=["use-c"],
            prohibited_uses=["use-d"],
            summary="Stored LLM summary text.",
            confidence="high",
        )

        report = _build_report_from_cache(
            params,
            "123 Main St",
            _make_geo(),
            _make_prop(zoning_code="RM-12"),
            ["Sec. 500"],
            [_make_result()],
            cached_data=cached_data,
        )

        assert report.zoning_description == "Stored LLM description"
        assert report.allowed_uses == ["use-a", "use-b"]
        assert report.conditional_uses == ["use-c"]
        assert report.prohibited_uses == ["use-d"]
        assert report.summary == "Stored LLM summary text."
        assert report.confidence == "high"

    def test_build_report_from_cache_uses_llm_confidence_not_hardcoded(self):
        clear_zoning_params_cache()
        cached_data = CachedZoningData(
            numeric_params=NumericZoningParams(),
            confidence="high",
            summary="test",
        )

        report = _build_report_from_cache(
            NumericZoningParams(),
            "123 Main St",
            _make_geo(),
            _make_prop(zoning_code="RM-12"),
            ["Sec. 500"],
            [_make_result()],
            cached_data=cached_data,
        )
        assert report.confidence == "high"

    def test_build_report_from_cache_fallback_no_cached_data(self):
        clear_zoning_params_cache()
        result = _make_result(
            zone_codes=["RM-12"],
            chunk_text="Maximum height is 35 feet. Density limit 12 units/acre.",
        )
        report = _build_report_from_cache(
            NumericZoningParams(max_height_ft=35.0),
            "123 Main St",
            _make_geo(),
            _make_prop(zoning_code="RM-12"),
            ["Sec. 500"],
            [result],
            cached_data=None,
        )
        assert report.confidence == "medium"
        assert "Cached zoning analysis" in report.summary
        assert report.max_height == "35 ft"

    @pytest.mark.asyncio
    async def test_cached_data_extracted_at_set_automatically(self):
        clear_zoning_params_cache()
        data = CachedZoningData(numeric_params=NumericZoningParams(), confidence="low", summary="t")
        await _store_zoning_params(
            "Broward", "Miramar", "RS-4", data, chunk_ids=["1"], model_id="gpt-4.1"
        )
        retrieved = _get_cached_zoning_data(
            "Broward", "Miramar", "RS-4", chunk_ids=["1"], model_id="gpt-4.1"
        )
        assert retrieved is not None
        assert retrieved.extracted_at
        assert "T" in retrieved.extracted_at

    @pytest.mark.asyncio
    async def test_stored_confidence_preserved_not_overwritten(self):
        clear_zoning_params_cache()
        for conf in ["high", "medium", "low"]:
            data = CachedZoningData(
                numeric_params=NumericZoningParams(), confidence=conf, summary="t"
            )
            await _store_zoning_params(
                "Broward", "Miramar", f"Z-{conf}", data, chunk_ids=["1"], model_id="gpt-4.1"
            )
            cached_params = _get_cached_zoning_params("Broward", "Miramar", f"Z-{conf}")
            assert cached_params is not None

            cached_data = _get_cached_zoning_data(
                "Broward", "Miramar", f"Z-{conf}", chunk_ids=["1"], model_id="gpt-4.1"
            )
            assert cached_data is not None
            assert cached_data.confidence == conf


# ── Task 1.5: LLM output validation tests ──


class TestValidateNumericParams:
    def test_density_too_high_flags_warning(self):
        params = NumericZoningParams(max_density_units_per_acre=300.0)
        warnings = _validate_numeric_params(params)
        assert len(warnings) == 1
        assert "300" in warnings[0]
        assert "200 du/acre" in warnings[0]

    def test_far_too_high_flags_warning(self):
        params = NumericZoningParams(far=8.0)
        warnings = _validate_numeric_params(params)
        assert len(warnings) == 1
        assert "8.0" in warnings[0]
        assert "5.0" in warnings[0]

    def test_height_sf_zone_flags_warning(self):
        params = NumericZoningParams(max_height_ft=120.0)
        warnings = _validate_numeric_params(params, zoning_code="RS-4")
        assert len(warnings) == 1
        assert "120" in warnings[0]
        assert "single-family zone (RS-4)" in warnings[0]

    def test_height_commercial_zone_no_warning(self):
        params = NumericZoningParams(max_height_ft=120.0)
        warnings = _validate_numeric_params(params, zoning_code="C-2")
        assert len(warnings) == 0

    def test_lot_coverage_over_100_flags_warning(self):
        params = NumericZoningParams(max_lot_coverage_pct=150.0)
        warnings = _validate_numeric_params(params)
        assert len(warnings) == 1
        assert "150.0%" in warnings[0]
        assert "parsing error" in warnings[0]

    def test_normal_values_zero_warnings(self):
        params = NumericZoningParams(
            max_density_units_per_acre=6.0,
            far=0.5,
            max_height_ft=35.0,
        )
        warnings = _validate_numeric_params(params, zoning_code="RS-4")
        assert warnings == []

    @pytest.mark.asyncio
    async def test_validation_warnings_present_in_report_when_empty(self):
        report = await _build_report(
            {"zoning_district": "R-1", "summary": "ok", "confidence": "high"},
            "123 Main St",
            _make_geo(),
            _make_prop(),
            ["Sec. 500"],
        )
        assert report.validation_warnings == []


# ── Task 1.6: Geocode accuracy three-tier tests ──


class TestGeocodeAccuracy:
    @pytest.mark.asyncio
    async def test_accuracy_065_degraded_proceeds_with_low_confidence(self):
        """Accuracy 0.65 → degraded mode: proceed with confidence capped at low."""
        from plotlot.pipeline.lookup import _pipeline_cache

        _pipeline_cache.clear()
        mock_session = AsyncMock()

        async def mock_call_llm(messages, tools=None, temperature=0.1):
            return {
                "content": json.dumps(
                    {
                        "zoning_district": "RS-4",
                        "summary": "test",
                        "confidence": "high",
                    }
                ),
                "tool_calls": [],
            }

        geo = _make_geo(accuracy=0.65)

        with (
            patch("plotlot.pipeline.lookup.geocode_address", return_value=geo),
            patch("plotlot.pipeline.lookup.lookup_property", return_value=_make_prop()),
            patch("plotlot.pipeline.lookup.hybrid_search", return_value=[_make_result()]),
            patch("plotlot.pipeline.lookup.get_session", return_value=mock_session),
            patch("plotlot.retrieval.llm.call_llm", side_effect=mock_call_llm),
        ):
            result = await lookup_address("123 Main St, Some City, FL")

        assert result is not None
        assert result.confidence == "low"
        assert geo.get("accuracy_warning") is True

    @pytest.mark.asyncio
    async def test_accuracy_03_rejects_with_valueerror(self):
        """Accuracy 0.3 → rejects with ValueError."""
        from plotlot.pipeline.lookup import _pipeline_cache

        _pipeline_cache.clear()

        geo = _make_geo(accuracy=0.3)

        with (
            patch("plotlot.pipeline.lookup.geocode_address", return_value=geo),
            patch("plotlot.pipeline.lookup.lookup_property", return_value=_make_prop()),
            patch("plotlot.pipeline.lookup.hybrid_search", return_value=[_make_result()]),
            patch("plotlot.pipeline.lookup.get_session", return_value=AsyncMock()),
            pytest.raises(ValueError, match="Could not locate this address"),
        ):
            await lookup_address("123 Main St, Some City, FL")

    @pytest.mark.asyncio
    async def test_accuracy_092_proceeds_normally(self):
        """Accuracy 0.92 → normal report, no warning flag."""
        from plotlot.pipeline.lookup import _pipeline_cache

        _pipeline_cache.clear()
        mock_session = AsyncMock()

        async def mock_call_llm(messages, tools=None, temperature=0.1):
            return {
                "content": json.dumps(
                    {
                        "zoning_district": "RS-4",
                        "summary": "test",
                        "confidence": "high",
                    }
                ),
                "tool_calls": [],
            }

        geo = _make_geo(accuracy=0.92)

        with (
            patch("plotlot.pipeline.lookup.geocode_address", return_value=geo),
            patch("plotlot.pipeline.lookup.lookup_property", return_value=_make_prop()),
            patch("plotlot.pipeline.lookup.hybrid_search", return_value=[_make_result()]),
            patch("plotlot.pipeline.lookup.get_session", return_value=mock_session),
            patch("plotlot.retrieval.llm.call_llm", side_effect=mock_call_llm),
        ):
            result = await lookup_address("123 Main St, Some City, FL")

        assert result is not None
        assert result.confidence == "high"
        assert geo.get("accuracy_warning") is not True


# ── Task 1.9: Cached params provenance tests ──


class TestCachedProvenance:
    def test_cached_report_with_extracted_at_shows_date(self):
        clear_zoning_params_cache()
        cached_data = CachedZoningData(
            numeric_params=NumericZoningParams(max_density_units_per_acre=12.0),
            extracted_at="2026-06-15T10:00:00Z",
        )
        report = _build_report_from_cache(
            NumericZoningParams(max_density_units_per_acre=12.0),
            "123 Main St",
            _make_geo(),
            _make_prop(zoning_code="RM-12"),
            ["Sec. 500"],
            [_make_result()],
            cached_data=cached_data,
        )
        assert "2026-06-15T10:00:00Z" in report.summary
        assert "extracted by LLM on" in report.summary

    def test_cached_report_empty_extracted_at_shows_unknown_date(self):
        clear_zoning_params_cache()
        cached_data = CachedZoningData(
            numeric_params=NumericZoningParams(max_density_units_per_acre=12.0),
            extracted_at="",
        )
        report = _build_report_from_cache(
            NumericZoningParams(max_density_units_per_acre=12.0),
            "123 Main St",
            _make_geo(),
            _make_prop(zoning_code="RM-12"),
            ["Sec. 500"],
            [_make_result()],
            cached_data=cached_data,
        )
        assert "unknown date" in report.summary

    @pytest.mark.asyncio
    async def test_fresh_report_no_cached_data_no_provenance_text(self):
        report = await _build_report(
            {"zoning_district": "R-1", "summary": "Fresh analysis", "confidence": "medium"},
            "123 Main St",
            _make_geo(),
            _make_prop(),
            ["Sec. 500"],
        )
        assert "extracted by LLM on" not in report.summary
        assert "unknown date" not in report.summary
        assert report.summary == "Fresh analysis"


class TestZonePrefixDefaults:
    """Conservative zone-prefix-based defaults when LLM extracts no numeric params."""

    def test_residential_r1(self):
        p = _zone_prefix_defaults("R-1", None)
        assert p.far == 0.5
        assert p.max_height_ft == 35
        assert p.max_lot_coverage_pct == 40
        assert p.max_stories == 3

    def test_commercial_c2(self):
        p = _zone_prefix_defaults("C-2", None)
        assert p.far == 1.5
        assert p.max_height_ft == 45
        assert p.max_lot_coverage_pct == 70

    def test_multifamily_rm2(self):
        p = _zone_prefix_defaults("RM-2", None)
        assert p.far == 1.0
        assert p.max_height_ft == 45

    def test_industrial_i1(self):
        p = _zone_prefix_defaults("I-1", None)
        assert p.far == 2.0
        assert p.max_lot_coverage_pct == 80

    def test_form_based_t5o(self):
        p = _zone_prefix_defaults("T5-O", None)
        assert p.far == 1.5  # commercial

    def test_unknown_xx1(self):
        p = _zone_prefix_defaults("XX-1", None)
        assert p.far == 0.5  # conservative default
        assert p.max_height_ft == 35

    def test_no_district(self):
        p = _zone_prefix_defaults(None, None)
        assert p.far == 0.5  # conservative default
        assert p.max_stories == 3

    def test_extract_numeric_params_fallback(self):
        """When all fields are None and district=RS-4, returns NumericZoningParams not None."""
        params = _extract_numeric_params({"zoning_district": "RS-4"})
        assert isinstance(params, NumericZoningParams)
        assert params is not None
        assert params.far == 0.5
        assert params.max_height_ft == 35
        assert params.max_lot_coverage_pct == 40
