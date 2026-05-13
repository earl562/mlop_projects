"""Tests for LLM provider fallback (OpenAI -> OpenRouter)."""

from unittest.mock import AsyncMock, patch

import pytest


class TestLLMFallback:
    @pytest.mark.asyncio
    async def test_call_llm_falls_back_to_openrouter_when_openai_returns_none(self):
        from plotlot.retrieval import llm

        messages = [{"role": "user", "content": "hi"}]
        openai_mock = AsyncMock(return_value=None)
        openrouter_resp = {"content": "ok", "tool_calls": []}
        openrouter_mock = AsyncMock(return_value=openrouter_resp)

        with (
            patch.object(llm, "_call_openai", openai_mock),
            patch.object(llm, "_call_openrouter", openrouter_mock),
        ):
            result = await llm.call_llm(messages)

        assert result == openrouter_resp
        assert openai_mock.await_count == 1
        assert openrouter_mock.await_count == 1

    @pytest.mark.asyncio
    async def test_call_llm_does_not_call_openrouter_when_openai_succeeds(self):
        from plotlot.retrieval import llm

        messages = [{"role": "user", "content": "hi"}]
        openai_resp = {"content": "from-openai", "tool_calls": []}
        openai_mock = AsyncMock(return_value=openai_resp)
        openrouter_mock = AsyncMock(return_value={"content": "from-openrouter", "tool_calls": []})

        with (
            patch.object(llm, "_call_openai", openai_mock),
            patch.object(llm, "_call_openrouter", openrouter_mock),
        ):
            result = await llm.call_llm(messages)

        assert result == openai_resp
        assert openai_mock.await_count == 1
        assert openrouter_mock.await_count == 0
