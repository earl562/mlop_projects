"""Tests for LLM client (NVIDIA primary, OpenRouter fallback)."""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from plotlot.core.types import SearchResult, Setbacks, ZoningReport
from plotlot.retrieval.llm import (
    _build_user_prompt,
    _parse_llm_content,
    analyze_zoning,
    llm_response_to_report,
)


def _make_result(**kwargs) -> SearchResult:
    defaults = {
        "section": "Sec. 500",
        "section_title": "Permitted Uses",
        "zone_codes": ["RS-4"],
        "chunk_text": "Single-family residential is permitted in the RS-4 district.",
        "score": 0.85,
        "municipality": "Miramar",
    }
    defaults.update(kwargs)
    return SearchResult(**defaults)


class TestBuildUserPrompt:
    def test_includes_address(self):
        prompt = _build_user_prompt("123 Main St", "Miramar", "Broward", [_make_result()])
        assert "123 Main St" in prompt

    def test_includes_municipality(self):
        prompt = _build_user_prompt("123 Main St", "Miramar", "Broward", [_make_result()])
        assert "Miramar" in prompt

    def test_includes_chunk_text(self):
        prompt = _build_user_prompt("123 Main St", "Miramar", "Broward", [_make_result()])
        assert "Single-family residential" in prompt

    def test_includes_zone_codes(self):
        prompt = _build_user_prompt("123 Main St", "Miramar", "Broward", [_make_result()])
        assert "RS-4" in prompt

    def test_multiple_chunks(self):
        results = [_make_result(section=f"Sec. {i}") for i in range(3)]
        prompt = _build_user_prompt("123 Main St", "Miramar", "Broward", results)
        assert "Chunk 1" in prompt
        assert "Chunk 3" in prompt


class TestParseLlmContent:
    def test_plain_json(self):
        result = _parse_llm_content('{"zoning_district": "RS-4"}')
        assert result["zoning_district"] == "RS-4"

    def test_with_markdown_fences(self):
        content = '```json\n{"zoning_district": "RS-4"}\n```'
        result = _parse_llm_content(content)
        assert result["zoning_district"] == "RS-4"

    def test_with_whitespace(self):
        result = _parse_llm_content('  \n  {"key": "val"}  \n  ')
        assert result["key"] == "val"


class TestAnalyzeZoning:
    @pytest.mark.asyncio
    async def test_no_results_returns_empty(self):
        result = await analyze_zoning("123 Main St", "Miramar", "Broward", [])
        assert result == {}

    @pytest.mark.asyncio
    async def test_nvidia_primary_success(self):
        llm_response = {
            "choices": [{"message": {"content": json.dumps({
                "zoning_district": "RS-4",
                "summary": "Residential district",
                "confidence": "high",
            })}}]
        }

        mock_resp = MagicMock()
        mock_resp.json.return_value = llm_response
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post.return_value = mock_resp
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("plotlot.retrieval.llm.httpx.AsyncClient", return_value=mock_client), \
             patch("plotlot.retrieval.llm.settings") as mock_settings:
            mock_settings.nvidia_api_key = "test_nvidia_key"
            mock_settings.openrouter_api_key = "test_or_key"

            result = await analyze_zoning(
                "123 Main St", "Miramar", "Broward", [_make_result()],
            )

        assert result["zoning_district"] == "RS-4"
        # Should only call once (NVIDIA succeeds)
        assert mock_client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_nvidia_fails_openrouter_fallback(self):
        import httpx

        nvidia_error = httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=MagicMock(status_code=500),
        )
        # Make the response text attribute available
        nvidia_error.response.text = "Internal Server Error"

        or_response = MagicMock()
        or_response.json.return_value = {
            "choices": [{"message": {"content": json.dumps({
                "zoning_district": "B-2",
                "confidence": "medium",
            })}}]
        }
        or_response.raise_for_status = MagicMock()

        call_count = {"n": 0}

        async def mock_post(url, **kwargs):
            call_count["n"] += 1
            if "nvidia" in url:
                raise nvidia_error
            return or_response

        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        with patch("plotlot.retrieval.llm.httpx.AsyncClient", return_value=mock_client), \
             patch("plotlot.retrieval.llm.settings") as mock_settings, \
             patch("plotlot.retrieval.llm.BASE_DELAY", 0.01):
            mock_settings.nvidia_api_key = "test_nvidia_key"
            mock_settings.openrouter_api_key = "test_or_key"

            result = await analyze_zoning(
                "123 Main St", "Miramar", "Broward", [_make_result()],
            )

        assert result["zoning_district"] == "B-2"
        # NVIDIA retries (3 + 1 final) + OpenRouter (1 success)
        assert call_count["n"] >= 2

    @pytest.mark.asyncio
    async def test_no_api_keys(self):
        with patch("plotlot.retrieval.llm.settings") as mock_settings:
            mock_settings.nvidia_api_key = ""
            mock_settings.openrouter_api_key = ""

            result = await analyze_zoning(
                "123 Main St", "Miramar", "Broward", [_make_result()],
            )

        assert result == {}


class TestLlmResponseToReport:
    def test_full_response(self):
        raw = {
            "zoning_district": "RS-4",
            "zoning_description": "Single Family Residential",
            "allowed_uses": ["Single-family homes"],
            "conditional_uses": ["Home offices"],
            "prohibited_uses": ["Industrial"],
            "setbacks": {"front": "25 ft", "side": "10 ft", "rear": "20 ft"},
            "max_height": "35 ft",
            "max_density": "5 du/acre",
            "floor_area_ratio": "0.50",
            "lot_coverage": "40%",
            "min_lot_size": "7,500 sq ft",
            "parking_requirements": "2 spaces per dwelling unit",
            "summary": "Residential single-family district.",
            "confidence": "high",
        }

        report = llm_response_to_report(
            raw,
            address="123 Main St",
            formatted_address="123 Main St, Miramar, FL 33023",
            municipality="Miramar",
            county="Broward",
            lat=25.977,
            lng=-80.232,
            sources=["Sec. 500 — Permitted Uses"],
        )

        assert isinstance(report, ZoningReport)
        assert report.zoning_district == "RS-4"
        assert report.setbacks.front == "25 ft"
        assert report.allowed_uses == ["Single-family homes"]
        assert report.confidence == "high"
        assert report.municipality == "Miramar"

    def test_empty_response(self):
        report = llm_response_to_report(
            {},
            address="123 Main St",
            formatted_address="123 Main St",
            municipality="Miramar",
            county="Broward",
            lat=None,
            lng=None,
            sources=[],
        )

        assert report.zoning_district == ""
        assert report.allowed_uses == []
        assert isinstance(report.setbacks, Setbacks)
        assert report.confidence == "low"
