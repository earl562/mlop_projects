"""Unit tests for Tier 2: Agent Intelligence features.

Tests:
1. AnalyzeRequest schema accepts skip_steps + deal_type
2. Intent classification (keyword-based)
3. skip_steps parameter is respected in pipeline
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from plotlot.api.schemas import AnalyzeRequest


# ---------------------------------------------------------------------------
# Schema Tests
# ---------------------------------------------------------------------------


class TestAnalyzeRequestSchema:
    """Test the updated AnalyzeRequest with skip_steps and deal_type."""

    def test_default_values(self):
        req = AnalyzeRequest(address="123 Main St, Miami, FL 33101")
        assert req.deal_type == "land_deal"
        assert req.skip_steps == []

    def test_custom_deal_type(self):
        req = AnalyzeRequest(
            address="123 Main St, Miami, FL 33101",
            deal_type="wholesale",
        )
        assert req.deal_type == "wholesale"

    def test_skip_steps(self):
        req = AnalyzeRequest(
            address="123 Main St, Miami, FL 33101",
            skip_steps=["comps", "proforma"],
        )
        assert req.skip_steps == ["comps", "proforma"]

    def test_invalid_deal_type_rejected(self):
        with pytest.raises(Exception):
            AnalyzeRequest(
                address="123 Main St, Miami, FL 33101",
                deal_type="invalid_type",
            )

    def test_all_deal_types_valid(self):
        for dt in ["land_deal", "wholesale", "creative_finance", "hybrid"]:
            req = AnalyzeRequest(address="123 Main St, Miami, FL", deal_type=dt)
            assert req.deal_type == dt

    def test_full_request_serialization(self):
        req = AnalyzeRequest(
            address="7940 Plantation Blvd, Miramar, FL 33023",
            deal_type="creative_finance",
            skip_steps=["calculation"],
        )
        data = req.model_dump()
        assert data["address"] == "7940 Plantation Blvd, Miramar, FL 33023"
        assert data["deal_type"] == "creative_finance"
        assert data["skip_steps"] == ["calculation"]


# ---------------------------------------------------------------------------
# Intent Classification Tests
# ---------------------------------------------------------------------------


class TestIntentClassification:
    """Test the keyword-based intent classifier."""

    def setup_method(self):
        from plotlot.api.chat import _classify_intent

        self._classify = _classify_intent

    def test_zoning_intent(self):
        result = self._classify("What is the zoning for 123 Main St?")
        assert result.intent == "zoning_lookup"

    def test_setback_intent(self):
        result = self._classify("What are the setback requirements?")
        assert result.intent == "zoning_lookup"

    def test_deal_analysis_intent(self):
        result = self._classify("I want to wholesale this property with a MAO of 70%")
        assert result.intent == "deal_analysis"

    def test_document_generation_intent(self):
        result = self._classify("Generate an LOI for this deal")
        assert result.intent == "document_generation"

    def test_general_question_intent(self):
        result = self._classify("Hello, how are you?")
        assert result.intent == "general_question"

    def test_wholesale_deal_type(self):
        result = self._classify("I want to wholesale this property")
        assert result.deal_type == "wholesale"

    def test_creative_finance_deal_type(self):
        result = self._classify("Subject to deal with seller financing")
        assert result.deal_type == "creative_finance"

    def test_hybrid_deal_type(self):
        result = self._classify("Looking at a hybrid combination deal")
        assert result.deal_type == "hybrid"

    def test_land_deal_type(self):
        result = self._classify("What is the max units for this land deal development?")
        assert result.deal_type == "land_deal"

    def test_no_deal_type_for_general(self):
        result = self._classify("Tell me about Miami weather")
        assert result.deal_type is None

    def test_document_with_deal_keywords(self):
        result = self._classify("Draft a purchase agreement for this deal")
        assert result.intent == "document_generation"

    def test_proforma_export_is_document(self):
        result = self._classify("Create a pro forma spreadsheet and export the comps")
        assert result.intent == "document_generation"

    def test_confidence_increases_with_keywords(self):
        simple = self._classify("zoning")
        complex_msg = self._classify("What is the zoning setback density for this lot?")
        assert complex_msg.confidence >= simple.confidence


# ---------------------------------------------------------------------------
# Intent Context Builder Tests
# ---------------------------------------------------------------------------


class TestIntentContextBuilder:
    """Test the system prompt context injection."""

    def test_zoning_context_mentions_tools(self):
        from plotlot.api.chat import IntentClassification, _build_intent_context

        ic = IntentClassification(intent="zoning_lookup")
        ctx = _build_intent_context(ic)
        assert "zoning" in ctx.lower()
        assert "geocode" in ctx.lower()

    def test_deal_context_mentions_comps(self):
        from plotlot.api.chat import IntentClassification, _build_intent_context

        ic = IntentClassification(intent="deal_analysis", deal_type="wholesale")
        ctx = _build_intent_context(ic)
        assert "comparable" in ctx.lower() or "comps" in ctx.lower()
        assert "Wholesale" in ctx

    def test_document_context(self):
        from plotlot.api.chat import IntentClassification, _build_intent_context

        ic = IntentClassification(intent="document_generation")
        ctx = _build_intent_context(ic)
        assert "generate_document" in ctx


# ---------------------------------------------------------------------------
# Pipeline skip_steps SSE Tests
# ---------------------------------------------------------------------------


class TestPipelineSkipSteps:
    """Test that skip_steps parameter works in the streaming pipeline."""

    @pytest.fixture
    def mock_pipeline(self):
        """Mock all pipeline dependencies."""
        with (
            patch("plotlot.api.routes.geocode_address") as mock_geo,
            patch("plotlot.api.routes.lookup_property") as mock_prop,
            patch("plotlot.api.routes.hybrid_search") as mock_search,
            patch("plotlot.api.routes._agentic_analysis") as mock_analysis,
            patch("plotlot.api.routes.get_session") as mock_session,
            patch("plotlot.api.routes.get_cached_report", return_value=None),
            patch("plotlot.api.routes.cache_report", new_callable=AsyncMock),
            patch("plotlot.api.routes.start_run"),
            patch("plotlot.api.routes.log_params"),
            patch("plotlot.api.routes.log_metrics"),
            patch("plotlot.api.routes.set_tag"),
            patch("plotlot.api.routes.log_prompt_to_run"),
        ):
            mock_geo.return_value = {
                "municipality": "Miramar",
                "county": "Broward",
                "lat": 25.97,
                "lng": -80.23,
                "accuracy": 1.0,
                "formatted_address": "7940 Plantation Blvd, Miramar, FL 33023",
            }

            from plotlot.core.types import PropertyRecord, ZoningReport, NumericZoningParams

            mock_prop.return_value = PropertyRecord(
                folio="1234",
                address="7940 PLANTATION BLVD",
                municipality="Miramar",
                county="Broward",
                lot_size_sqft=10000,
                zoning_code="RS-4",
                lat=25.97,
                lng=-80.23,
            )

            mock_session_obj = AsyncMock()
            mock_session.return_value = mock_session_obj

            mock_search.return_value = []

            mock_analysis.return_value = ZoningReport(
                address="7940 Plantation Blvd, Miramar, FL 33023",
                formatted_address="7940 Plantation Blvd, Miramar, FL 33023",
                municipality="Miramar",
                county="Broward",
                zoning_district="RS-4",
                zoning_description="Single Family Residential",
                numeric_params=NumericZoningParams(
                    max_density_units_per_acre=4.0,
                    max_height_ft=35.0,
                    setback_front_ft=25.0,
                    setback_side_ft=7.5,
                    setback_rear_ft=25.0,
                ),
                property_record=mock_prop.return_value,
                sources=["test"],
                confidence="high",
            )

            yield

    @pytest.mark.asyncio
    async def test_skip_comps_and_proforma(self, mock_pipeline):
        """When skip_steps includes comps and proforma, those steps emit 'Skipped'."""
        from plotlot.api.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/analyze/stream",
                json={
                    "address": "7940 Plantation Blvd, Miramar, FL 33023",
                    "skip_steps": ["comps", "proforma"],
                },
            )
            assert response.status_code == 200

            events = []
            for line in response.text.split("\n"):
                if line.startswith("data: "):
                    try:
                        events.append(json.loads(line[6:]))
                    except json.JSONDecodeError:
                        pass

            # Check that comps and proforma were skipped
            comps_events = [e for e in events if e.get("step") == "comps"]
            proforma_events = [e for e in events if e.get("step") == "proforma"]

            assert any(e.get("message") == "Skipped" for e in comps_events), (
                f"Expected 'Skipped' for comps, got {comps_events}"
            )
            assert any(e.get("message") == "Skipped" for e in proforma_events), (
                f"Expected 'Skipped' for proforma, got {proforma_events}"
            )

    @pytest.mark.asyncio
    async def test_thinking_events_emitted(self, mock_pipeline):
        """Thinking events should be emitted after analysis step."""
        from plotlot.api.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/analyze/stream",
                json={"address": "7940 Plantation Blvd, Miramar, FL 33023"},
            )
            assert response.status_code == 200

            # Parse SSE events
            thinking_events = []
            event_type = ""
            for line in response.text.split("\n"):
                if line.startswith("event: "):
                    event_type = line[7:].strip()
                elif line.startswith("data: ") and event_type == "thinking":
                    try:
                        thinking_events.append(json.loads(line[6:]))
                    except json.JSONDecodeError:
                        pass
                    event_type = ""

            assert len(thinking_events) > 0, "Expected at least one thinking event"
            assert thinking_events[0]["step"] == "analysis"
            assert len(thinking_events[0]["thoughts"]) > 0

    @pytest.mark.asyncio
    async def test_deal_type_accepted(self, mock_pipeline):
        """deal_type parameter should be accepted without error."""
        from plotlot.api.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/analyze/stream",
                json={
                    "address": "7940 Plantation Blvd, Miramar, FL 33023",
                    "deal_type": "wholesale",
                },
            )
            assert response.status_code == 200
