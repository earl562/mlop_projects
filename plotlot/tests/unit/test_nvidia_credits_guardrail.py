"""Tests for NVIDIA credits-exhausted guardrail in the embedding pipeline."""

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from plotlot.core.errors import NvidiaCreditsExhaustedError
from plotlot.ingestion.embedder import _embed_batch


def _make_response(status_code: int, json_body: dict | None = None) -> httpx.Response:
    request = httpx.Request("POST", "https://integrate.api.nvidia.com/v1/embeddings")
    return httpx.Response(status_code, json=json_body or {}, request=request)


class TestNvidiaCreditsGuardrail:
    @pytest.mark.asyncio
    async def test_402_raises_credits_exhausted(self):
        """HTTP 402 during embedding must raise NvidiaCreditsExhaustedError immediately."""
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            return_value=_make_response(402, {"error": "Payment Required"})
        )

        with pytest.raises(NvidiaCreditsExhaustedError) as exc_info:
            await _embed_batch(mock_client, ["test text"], {}, "passage")

        assert "402" in str(exc_info.value) or "credits" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_402_does_not_retry(self):
        """Credits exhausted should NOT be retried — stop immediately."""
        call_count = 0

        async def counting_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return _make_response(402)

        mock_client = AsyncMock()
        mock_client.post = counting_post

        with pytest.raises(NvidiaCreditsExhaustedError):
            await _embed_batch(mock_client, ["test text"], {}, "passage")

        # Should have called once and stopped — not retried MAX_RETRIES times
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_429_still_retries(self):
        """HTTP 429 rate limit should still retry, not be treated as credits exhausted."""
        responses = [
            _make_response(429),
            _make_response(429),
            _make_response(200, {"data": [{"embedding": [0.1] * 1024}]}),
        ]
        response_iter = iter(responses)

        async def mock_post(*args, **kwargs):
            return next(response_iter)

        mock_client = AsyncMock()
        mock_client.post = mock_post

        with patch("plotlot.ingestion.embedder.asyncio.sleep", new_callable=AsyncMock):
            result = await _embed_batch(mock_client, ["test text"], {}, "passage")

        assert len(result) == 1
        assert len(result[0]) == 1024

    @pytest.mark.asyncio
    async def test_successful_embedding_not_affected(self):
        """Normal 200 response should return embeddings as before."""
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(
            return_value=_make_response(
                200,
                {"data": [{"embedding": [0.5] * 1024}, {"embedding": [0.3] * 1024}]},
            )
        )

        result = await _embed_batch(mock_client, ["text one", "text two"], {}, "passage")

        assert len(result) == 2
        assert len(result[0]) == 1024


class TestNvidiaCreditsExhaustedError:
    def test_error_message_contains_upgrade_url(self):
        err = NvidiaCreditsExhaustedError()
        assert "build.nvidia.com" in str(err)

    def test_error_message_mentions_checkpoint(self):
        err = NvidiaCreditsExhaustedError()
        assert "checkpoint" in str(err).lower()

    def test_is_fatal_error(self):
        from plotlot.core.errors import FatalError

        assert isinstance(NvidiaCreditsExhaustedError(), FatalError)
