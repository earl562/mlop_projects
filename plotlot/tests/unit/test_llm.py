"""Tests for the OpenAI SDK-backed LLM client."""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from plotlot.core.types import SearchResult, Setbacks, ZoningReport
from plotlot.retrieval.llm import (
    _build_user_prompt,
    _convert_messages_for_anthropic,
    _convert_tool_calls_from_anthropic,
    _convert_tools_to_anthropic,
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


class TestToolConversion:
    def test_convert_tools_to_anthropic(self):
        openai_tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_zoning",
                    "description": "Search zoning code",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"],
                    },
                },
            }
        ]
        result = _convert_tools_to_anthropic(openai_tools)
        assert len(result) == 1
        assert result[0]["name"] == "search_zoning"
        assert result[0]["description"] == "Search zoning code"
        assert "properties" in result[0]["input_schema"]

    def test_convert_tool_calls_from_anthropic_dict(self):
        content_blocks = [
            {"type": "text", "text": "Let me search..."},
            {
                "type": "tool_use",
                "id": "tool_123",
                "name": "search_zoning",
                "input": {"query": "RS-4 setbacks"},
            },
        ]
        result = _convert_tool_calls_from_anthropic(content_blocks)
        assert len(result) == 1
        assert result[0]["id"] == "tool_123"
        assert result[0]["function"]["name"] == "search_zoning"
        assert json.loads(result[0]["function"]["arguments"]) == {"query": "RS-4 setbacks"}

    def test_convert_messages_for_anthropic(self):
        messages = [
            {"role": "system", "content": "You are a zoning expert."},
            {"role": "user", "content": "Analyze this property."},
            {
                "role": "assistant",
                "content": "I'll analyze it.",
                "tool_calls": [
                    {
                        "id": "tc_1",
                        "type": "function",
                        "function": {
                            "name": "search",
                            "arguments": '{"q":"RS-4"}',
                        },
                    },
                ],
            },
            {"role": "tool", "tool_call_id": "tc_1", "content": '{"status": "ok"}'},
        ]
        system, anthropic_msgs = _convert_messages_for_anthropic(messages)
        assert system == "You are a zoning expert."
        assert len(anthropic_msgs) == 3  # user, assistant, tool_result
        assert anthropic_msgs[0]["role"] == "user"
        assert anthropic_msgs[1]["role"] == "assistant"
        assert anthropic_msgs[2]["role"] == "user"
        assert anthropic_msgs[2]["content"][0]["type"] == "tool_result"


class TestAnalyzeZoning:
    @pytest.mark.asyncio
    async def test_no_results_returns_empty(self):
        result = await analyze_zoning("123 Main St", "Miramar", "Broward", [])
        assert result == {}

    @pytest.mark.asyncio
    async def test_openai_primary_success(self):
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps(
                        {
                            "zoning_district": "RS-4",
                            "summary": "Residential district",
                            "confidence": "high",
                        }
                    ),
                    tool_calls=[],
                ),
            )
        ]
        mock_response.usage = MagicMock(prompt_tokens=100, completion_tokens=50)

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with (
            patch("plotlot.retrieval.llm.settings") as mock_settings,
            patch("plotlot.retrieval.llm.AsyncOpenAI", return_value=mock_client),
        ):
            mock_settings.openai_api_key = "test_key"
            mock_settings.openai_access_token = ""
            mock_settings.use_codex_oauth = False
            mock_settings.openai_base_url = "https://api.openai.com/v1"
            mock_settings.openai_model = "gpt-4.1"
            mock_settings.openai_reasoning_effort = "medium"

            result = await analyze_zoning(
                "123 Main St",
                "Miramar",
                "Broward",
                [_make_result()],
            )

        assert result.get("zoning_district") == "RS-4"

    @pytest.mark.asyncio
    async def test_no_api_keys(self):
        with patch("plotlot.retrieval.llm.settings") as mock_settings:
            mock_settings.openai_api_key = ""
            mock_settings.openai_access_token = ""
            mock_settings.use_codex_oauth = False

            result = await analyze_zoning(
                "123 Main St",
                "Miramar",
                "Broward",
                [_make_result()],
            )

        assert result == {}

    @pytest.mark.asyncio
    async def test_oauth_access_token_is_accepted(self):
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps(
                        {
                            "zoning_district": "RS-4",
                            "summary": "From oauth",
                            "confidence": "medium",
                        }
                    ),
                    tool_calls=[],
                ),
            )
        ]
        mock_response.usage = MagicMock(prompt_tokens=50, completion_tokens=30)

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with (
            patch("plotlot.retrieval.llm.AsyncOpenAI", return_value=mock_client),
            patch("plotlot.retrieval.llm.settings") as mock_settings,
        ):
            mock_settings.openai_api_key = ""
            mock_settings.openai_access_token = "oauth-access-token"
            mock_settings.use_codex_oauth = False
            mock_settings.openai_base_url = "https://gateway.example.com/v1"
            mock_settings.openai_model = "gpt-4.1"
            mock_settings.openai_reasoning_effort = "medium"

            result = await analyze_zoning(
                "123 Main St",
                "Miramar",
                "Broward",
                [_make_result()],
            )

        assert result.get("zoning_district") == "RS-4"

    @pytest.mark.asyncio
    async def test_codex_oauth_uses_refreshable_token_provider(self):
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content=json.dumps(
                        {
                            "zoning_district": "RS-4",
                            "summary": "From codex oauth",
                            "confidence": "medium",
                        }
                    ),
                    tool_calls=[],
                ),
            )
        ]
        mock_response.usage = MagicMock(prompt_tokens=50, completion_tokens=30)

        mock_client = MagicMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        with (
            patch("plotlot.retrieval.llm.AsyncOpenAI", return_value=mock_client) as async_openai_ctor,
            patch("plotlot.retrieval.llm.has_saved_tokens", return_value=True),
            patch("plotlot.retrieval.llm.settings") as mock_settings,
        ):
            mock_settings.openai_api_key = ""
            mock_settings.openai_access_token = ""
            mock_settings.use_codex_oauth = True
            mock_settings.codex_auth_file = "~/.codex/auth.json"
            mock_settings.openai_oauth_client_id = "client_123"
            mock_settings.openai_oauth_token_url = "https://auth.openai.com/oauth/token"
            mock_settings.openai_base_url = "https://api.openai.com/v1"
            mock_settings.openai_model = "gpt-4.1"
            mock_settings.openai_reasoning_effort = "medium"

            result = await analyze_zoning(
                "123 Main St",
                "Miramar",
                "Broward",
                [_make_result()],
            )

        assert result.get("zoning_district") == "RS-4"
        _, client_kwargs = async_openai_ctor.call_args
        assert callable(client_kwargs["api_key"])
        _, kwargs = mock_client.chat.completions.create.await_args
        assert kwargs["model"] == "gpt-4.1"


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
            sources=["Sec. 500 -- Permitted Uses"],
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
