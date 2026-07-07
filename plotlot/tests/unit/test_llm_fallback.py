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


class TestFastExtraction:
    """call_llm_fast — Groq-first routing for the extraction loop (PLOTLOT_FAST_EXTRACTION)."""

    @pytest.mark.asyncio
    async def test_disabled_flag_delegates_to_call_llm(self):
        from plotlot.retrieval import llm

        messages = [{"role": "user", "content": "hi"}]
        delegate_resp = {"content": "from-primary", "tool_calls": []}
        call_llm_mock = AsyncMock(return_value=delegate_resp)
        groq_mock = AsyncMock(return_value={"content": "from-groq", "tool_calls": []})

        with (
            patch.object(llm.settings, "fast_extraction_enabled", False),
            patch.object(llm, "call_llm", call_llm_mock),
            patch.object(llm, "_call_groq", groq_mock),
        ):
            result = await llm.call_llm_fast(messages)

        assert result == delegate_resp
        assert call_llm_mock.await_count == 1
        assert groq_mock.await_count == 0

    @pytest.mark.asyncio
    async def test_enabled_flag_tries_groq_first_and_skips_primary(self):
        from plotlot.retrieval import llm

        messages = [{"role": "user", "content": "hi"}]
        groq_resp = {"content": "from-groq", "tool_calls": []}
        groq_mock = AsyncMock(return_value=groq_resp)
        openai_mock = AsyncMock(return_value={"content": "from-openai", "tool_calls": []})

        with (
            patch.object(llm.settings, "fast_extraction_enabled", True),
            patch.object(llm, "_call_groq", groq_mock),
            patch.object(llm, "_call_openai", openai_mock),
        ):
            result = await llm.call_llm_fast(messages)

        assert result == groq_resp
        assert groq_mock.await_count == 1
        assert openai_mock.await_count == 0

    @pytest.mark.asyncio
    async def test_enabled_flag_falls_back_to_primary_when_groq_unusable(self):
        from plotlot.retrieval import llm

        messages = [{"role": "user", "content": "hi"}]
        primary_resp = {"content": "from-primary", "tool_calls": []}
        groq_mock = AsyncMock(return_value=None)
        openai_mock = AsyncMock(return_value=primary_resp)

        with (
            patch.object(llm.settings, "fast_extraction_enabled", True),
            patch.object(llm, "_call_groq", groq_mock),
            patch.object(llm, "_call_openai", openai_mock),
        ):
            result = await llm.call_llm_fast(messages)

        assert result == primary_resp
        assert groq_mock.await_count == 1
        assert openai_mock.await_count == 1

    def test_groq_token_enabled_by_fast_extraction_flag(self):
        from plotlot.retrieval import llm

        with (
            patch.object(llm.settings, "groq_enabled_non_mainline", False),
            patch.object(llm.settings, "fast_extraction_enabled", True),
            patch.object(llm.settings, "groq_api_key", "gsk_test"),
        ):
            assert llm._get_groq_token() == "gsk_test"

    def test_groq_token_empty_when_both_flags_off(self):
        from plotlot.retrieval import llm

        with (
            patch.object(llm.settings, "groq_enabled_non_mainline", False),
            patch.object(llm.settings, "fast_extraction_enabled", False),
            patch.object(llm.settings, "groq_api_key", "gsk_test"),
        ):
            assert llm._get_groq_token() == ""
