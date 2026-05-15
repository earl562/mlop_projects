"""Tests for county-by-county ingestion and NVIDIA credit tracking."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# embedder call counter tests
# ---------------------------------------------------------------------------


class TestEmbedderCallCounter:
    def setup_method(self):
        from plotlot.ingestion import embedder
        embedder._api_calls_this_run = 0

    def test_initial_count_is_zero(self):
        from plotlot.ingestion.embedder import get_api_calls
        assert get_api_calls() == 0

    def test_reset_clears_counter(self):
        from plotlot.ingestion import embedder
        from plotlot.ingestion.embedder import get_api_calls, reset_api_calls
        embedder._api_calls_this_run = 42
        reset_api_calls()
        assert get_api_calls() == 0

    async def test_successful_embed_increments_counter(self):
        import httpx
        from plotlot.ingestion.embedder import _embed_batch, get_api_calls, reset_api_calls

        reset_api_calls()
        fake_embedding = [0.1] * 1024
        fake_response = MagicMock(spec=httpx.Response)
        fake_response.status_code = 200
        fake_response.raise_for_status = MagicMock()
        fake_response.json.return_value = {"data": [{"embedding": fake_embedding}]}

        fake_client = AsyncMock(spec=httpx.AsyncClient)
        fake_client.post.return_value = fake_response

        result = await _embed_batch(fake_client, ["test text"], {}, "passage")

        assert len(result) == 1
        assert get_api_calls() == 1

    async def test_multiple_batches_accumulate(self):
        import httpx
        from plotlot.ingestion.embedder import _embed_batch, get_api_calls, reset_api_calls

        reset_api_calls()
        fake_embedding = [0.1] * 1024
        fake_response = MagicMock(spec=httpx.Response)
        fake_response.status_code = 200
        fake_response.raise_for_status = MagicMock()
        fake_response.json.return_value = {"data": [{"embedding": fake_embedding}]}

        fake_client = AsyncMock(spec=httpx.AsyncClient)
        fake_client.post.return_value = fake_response

        await _embed_batch(fake_client, ["text 1"], {}, "passage")
        await _embed_batch(fake_client, ["text 2"], {}, "passage")
        await _embed_batch(fake_client, ["text 3"], {}, "passage")

        assert get_api_calls() == 3

    async def test_402_does_not_increment_counter(self):
        import httpx
        from plotlot.core.errors import NvidiaCreditsExhaustedError
        from plotlot.ingestion.embedder import _embed_batch, get_api_calls, reset_api_calls

        reset_api_calls()

        fake_request = MagicMock(spec=httpx.Request)
        fake_response = MagicMock(spec=httpx.Response)
        fake_response.status_code = 402
        fake_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "402", request=fake_request, response=fake_response
        )

        fake_client = AsyncMock(spec=httpx.AsyncClient)
        fake_client.post.return_value = fake_response

        with pytest.raises(NvidiaCreditsExhaustedError):
            await _embed_batch(fake_client, ["text"], {}, "passage")

        assert get_api_calls() == 0


# ---------------------------------------------------------------------------
# Credit persistence tests
# ---------------------------------------------------------------------------


class TestCreditPersistence:
    def test_load_returns_zero_when_no_file(self, tmp_path):
        from plotlot import cli
        original = cli._CREDITS_FILE
        cli._CREDITS_FILE = tmp_path / "nvidia_credits_used.json"
        try:
            assert cli._load_cumulative_credits() == 0
        finally:
            cli._CREDITS_FILE = original

    def test_save_and_load_roundtrip(self, tmp_path):
        from plotlot import cli
        original = cli._CREDITS_FILE
        cli._CREDITS_FILE = tmp_path / "nvidia_credits_used.json"
        try:
            cli._save_cumulative_credits(137)
            assert cli._load_cumulative_credits() == 137
        finally:
            cli._CREDITS_FILE = original

    def test_save_increments_accumulate(self, tmp_path):
        from plotlot import cli
        original = cli._CREDITS_FILE
        cli._CREDITS_FILE = tmp_path / "nvidia_credits_used.json"
        try:
            cli._save_cumulative_credits(50)
            cli._save_cumulative_credits(50 + 73)
            assert cli._load_cumulative_credits() == 123
        finally:
            cli._CREDITS_FILE = original

    def test_load_handles_corrupt_file(self, tmp_path):
        from plotlot import cli
        original = cli._CREDITS_FILE
        cli._CREDITS_FILE = tmp_path / "nvidia_credits_used.json"
        cli._CREDITS_FILE.write_text("not valid json")
        try:
            assert cli._load_cumulative_credits() == 0
        finally:
            cli._CREDITS_FILE = original


# ---------------------------------------------------------------------------
# ingest_county tests
# ---------------------------------------------------------------------------


class TestIngestCounty:
    async def test_raises_on_unknown_county(self):
        from plotlot.pipeline.ingest import ingest_county

        fake_config = MagicMock()
        fake_config.state = "CA"
        fake_config.county = "Sacramento"

        with patch(
            "plotlot.ingestion.discovery.get_municode_configs",
            new_callable=AsyncMock,
            return_value={"sacramento_ca": fake_config},
        ):
            with pytest.raises(ValueError, match="No municipalities found"):
                await ingest_county("CA", "nonexistent_county")

    async def test_filters_to_correct_county(self):
        from plotlot.pipeline.ingest import ingest_county

        sac_config = MagicMock()
        sac_config.state = "CA"
        sac_config.county = "Sacramento"
        sac_config.municipality = "Sacramento"

        sf_config = MagicMock()
        sf_config.state = "CA"
        sf_config.county = "San Francisco"
        sf_config.municipality = "San Francisco"

        configs = {
            "sacramento_ca": sac_config,
            "san_francisco_ca": sf_config,
        }

        ingested_keys: list[str] = []

        async def mock_ingest(key: str) -> int:
            ingested_keys.append(key)
            return 100

        with patch(
            "plotlot.ingestion.discovery.get_municode_configs",
            new_callable=AsyncMock,
            return_value=configs,
        ), patch("plotlot.pipeline.ingest.ingest_municipality", side_effect=mock_ingest):
            results = await ingest_county("CA", "sacramento")

        assert "sacramento_ca" in ingested_keys
        assert "san_francisco_ca" not in ingested_keys
        assert results["sacramento_ca"] == 100

    async def test_county_key_normalization(self):
        """'contra_costa' matches county 'Contra Costa'."""
        from plotlot.pipeline.ingest import ingest_county

        cc_config = MagicMock()
        cc_config.state = "CA"
        cc_config.county = "Contra Costa"
        cc_config.municipality = "Concord"

        async def mock_ingest(key: str) -> int:
            return 200

        with patch(
            "plotlot.ingestion.discovery.get_municode_configs",
            new_callable=AsyncMock,
            return_value={"concord_ca": cc_config},
        ), patch("plotlot.pipeline.ingest.ingest_municipality", side_effect=mock_ingest):
            results = await ingest_county("CA", "contra_costa")

        assert results["concord_ca"] == 200

    async def test_credits_exhausted_reraises(self):
        from plotlot.core.errors import NvidiaCreditsExhaustedError
        from plotlot.pipeline.ingest import ingest_county

        sac_config = MagicMock()
        sac_config.state = "CA"
        sac_config.county = "Sacramento"
        sac_config.municipality = "Sacramento"

        async def mock_ingest(key: str) -> int:
            raise NvidiaCreditsExhaustedError()

        with patch(
            "plotlot.ingestion.discovery.get_municode_configs",
            new_callable=AsyncMock,
            return_value={"sacramento_ca": sac_config},
        ), patch("plotlot.pipeline.ingest.ingest_municipality", side_effect=mock_ingest):
            with pytest.raises(NvidiaCreditsExhaustedError):
                await ingest_county("CA", "sacramento")

    async def test_non_credit_failures_continue(self):
        """A failed municipality doesn't stop the county run (unless credits exhausted)."""
        from plotlot.pipeline.ingest import ingest_county

        configs = {}
        for name, county in [("Sacramento", "Sacramento"), ("Elk Grove", "Sacramento")]:
            cfg = MagicMock()
            cfg.state = "CA"
            cfg.county = county
            cfg.municipality = name
            configs[name.lower().replace(" ", "_") + "_ca"] = cfg

        call_count = 0

        async def mock_ingest(key: str) -> int:
            nonlocal call_count
            call_count += 1
            if "elk_grove" in key:
                raise RuntimeError("scrape failed")
            return 150

        with patch(
            "plotlot.ingestion.discovery.get_municode_configs",
            new_callable=AsyncMock,
            return_value=configs,
        ), patch("plotlot.pipeline.ingest.ingest_municipality", side_effect=mock_ingest):
            results = await ingest_county("CA", "sacramento")

        assert call_count == 2
        assert results.get("elk_grove_ca", None) == 0 or "elk_grove_ca" in results
