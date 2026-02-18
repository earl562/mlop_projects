"""Tests for the ingestion pipeline module."""

from unittest.mock import AsyncMock, patch

import pytest

from plotlot.core.types import MUNICODE_CONFIGS, MunicodeConfig, RawSection
from plotlot.pipeline.ingest import _resolve_all_configs, _resolve_config, ingest_all, ingest_municipality


class TestResolveConfig:
    @pytest.mark.asyncio
    async def test_resolve_from_discovery(self):
        discovered = MunicodeConfig(
            municipality="Coral Gables", county="miami_dade",
            client_id=100, product_id=200, job_id=300, zoning_node_id="CG",
        )

        async def mock_get_configs():
            return {"coral_gables": discovered}

        with patch("plotlot.ingestion.discovery.get_municode_configs", side_effect=mock_get_configs):
            config = await _resolve_config("coral_gables")

        assert config.municipality == "Coral Gables"

    @pytest.mark.asyncio
    async def test_resolve_fallback(self):
        async def mock_get_configs():
            raise ConnectionError("API down")

        with patch("plotlot.ingestion.discovery.get_municode_configs", side_effect=mock_get_configs):
            config = await _resolve_config("miami_dade")

        assert config.municipality == "Unincorporated Miami-Dade"

    @pytest.mark.asyncio
    async def test_resolve_unknown_raises(self):
        async def mock_get_configs():
            return {}

        with patch("plotlot.ingestion.discovery.get_municode_configs", side_effect=mock_get_configs):
            with pytest.raises(ValueError, match="Unknown municipality key"):
                await _resolve_config("nonexistent_city")


class TestResolveAllConfigs:
    @pytest.mark.asyncio
    async def test_uses_discovery(self):
        discovered = {
            "coral_gables": MunicodeConfig(
                municipality="Coral Gables", county="miami_dade",
                client_id=100, product_id=200, job_id=300, zoning_node_id="CG",
            ),
        }

        async def mock_get_configs():
            return discovered

        with patch("plotlot.ingestion.discovery.get_municode_configs", side_effect=mock_get_configs):
            configs = await _resolve_all_configs()

        assert "coral_gables" in configs

    @pytest.mark.asyncio
    async def test_fallback_on_failure(self):
        async def mock_get_configs():
            raise ConnectionError("API down")

        with patch("plotlot.ingestion.discovery.get_municode_configs", side_effect=mock_get_configs):
            configs = await _resolve_all_configs()

        assert "miami_dade" in configs
        assert "fort_lauderdale" in configs


class TestIngestMunicipality:
    @pytest.mark.asyncio
    async def test_invalid_key_raises(self):
        async def mock_get_configs():
            return {}

        with patch("plotlot.ingestion.discovery.get_municode_configs", side_effect=mock_get_configs):
            with pytest.raises(ValueError, match="Unknown municipality key"):
                await ingest_municipality("nonexistent_city")

    def test_municode_configs_has_expected_keys(self):
        assert "miami_dade" in MUNICODE_CONFIGS
        assert "fort_lauderdale" in MUNICODE_CONFIGS

    def test_municode_config_fields(self):
        for key, config in MUNICODE_CONFIGS.items():
            assert config.municipality, f"{key} missing municipality"
            assert config.county, f"{key} missing county"
            assert config.client_id > 0, f"{key} invalid client_id"
            assert config.product_id > 0, f"{key} invalid product_id"
            assert config.job_id > 0, f"{key} invalid job_id"
            assert config.zoning_node_id, f"{key} missing zoning_node_id"

    @pytest.mark.asyncio
    async def test_ingest_empty_scrape(self):
        with patch("plotlot.ingestion.discovery.get_municode_configs", new_callable=AsyncMock) as mock_disc, \
             patch("plotlot.pipeline.ingest.MunicodeScraper") as MockScraper:

            mock_disc.return_value = dict(MUNICODE_CONFIGS)
            mock_instance = MockScraper.return_value
            mock_instance.scrape_zoning_chapter = AsyncMock(return_value=[])
            count = await ingest_municipality("miami_dade")

        assert count == 0

    @pytest.mark.asyncio
    async def test_ingest_full_pipeline(self):
        mock_section = RawSection(
            municipality="Unincorporated Miami-Dade",
            county="miami_dade",
            node_id="test_node",
            heading="Sec. 33-49. - Minimum lot requirements",
            parent_heading="Chapter 33 - ZONING",
            html_content="<p>The minimum lot width for RU-1 is 75 feet. The minimum lot area is 7,500 square feet. The maximum building height is 35 feet.</p>",
            depth=2,
        )

        mock_embedding = [0.1] * 1024

        with patch("plotlot.ingestion.discovery.get_municode_configs", new_callable=AsyncMock) as mock_disc, \
             patch("plotlot.pipeline.ingest.MunicodeScraper") as MockScraper, \
             patch("plotlot.pipeline.ingest.embed_texts", new_callable=AsyncMock) as mock_embed, \
             patch("plotlot.pipeline.ingest.init_db", new_callable=AsyncMock), \
             patch("plotlot.pipeline.ingest.get_session", new_callable=AsyncMock) as mock_get_session:

            mock_disc.return_value = dict(MUNICODE_CONFIGS)
            mock_instance = MockScraper.return_value
            mock_instance.scrape_zoning_chapter = AsyncMock(return_value=[mock_section])
            mock_embed.return_value = [mock_embedding]

            mock_session = AsyncMock()
            mock_get_session.return_value = mock_session

            count = await ingest_municipality("miami_dade")

        assert count == 1
        mock_session.add_all.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_ingest_rollback_on_error(self):
        mock_section = RawSection(
            municipality="Fort Lauderdale",
            county="broward",
            node_id="test",
            heading="Test Section",
            parent_heading=None,
            html_content="<p>Test content for rollback testing with enough characters to pass minimum.</p>",
            depth=1,
        )

        with patch("plotlot.ingestion.discovery.get_municode_configs", new_callable=AsyncMock) as mock_disc, \
             patch("plotlot.pipeline.ingest.MunicodeScraper") as MockScraper, \
             patch("plotlot.pipeline.ingest.embed_texts", new_callable=AsyncMock) as mock_embed, \
             patch("plotlot.pipeline.ingest.init_db", new_callable=AsyncMock), \
             patch("plotlot.pipeline.ingest.get_session", new_callable=AsyncMock) as mock_get_session:

            mock_disc.return_value = dict(MUNICODE_CONFIGS)
            mock_instance = MockScraper.return_value
            mock_instance.scrape_zoning_chapter = AsyncMock(return_value=[mock_section])
            mock_embed.return_value = [[0.1] * 1024]

            mock_session = AsyncMock()
            mock_session.commit.side_effect = Exception("DB error")
            mock_get_session.return_value = mock_session

            with pytest.raises(Exception, match="DB error"):
                await ingest_municipality("fort_lauderdale")

        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()


class TestIngestAll:
    @pytest.mark.asyncio
    async def test_ingest_all_uses_discovery(self):
        configs = {
            "test_city": MunicodeConfig(
                municipality="Test City", county="test",
                client_id=1, product_id=2, job_id=3, zoning_node_id="N",
            ),
        }

        with patch("plotlot.ingestion.discovery.get_municode_configs", new_callable=AsyncMock) as mock_disc, \
             patch("plotlot.pipeline.ingest.MunicodeScraper") as MockScraper:

            mock_disc.return_value = configs
            mock_instance = MockScraper.return_value
            mock_instance.scrape_zoning_chapter = AsyncMock(return_value=[])

            results = await ingest_all()

        assert isinstance(results, dict)
        assert "test_city" in results

    @pytest.mark.asyncio
    async def test_ingest_all_handles_failures(self):
        configs = {
            "good_city": MunicodeConfig(
                municipality="Good City", county="test",
                client_id=1, product_id=2, job_id=3, zoning_node_id="N",
            ),
            "bad_city": MunicodeConfig(
                municipality="Bad City", county="test",
                client_id=4, product_id=5, job_id=6, zoning_node_id="N2",
            ),
        }

        call_count = {"n": 0}

        async def mock_scrape(config):
            call_count["n"] += 1
            if config.municipality == "Bad City":
                raise ConnectionError("Scrape failed")
            return []

        with patch("plotlot.ingestion.discovery.get_municode_configs", new_callable=AsyncMock) as mock_disc, \
             patch("plotlot.pipeline.ingest.MunicodeScraper") as MockScraper:

            mock_disc.return_value = configs
            mock_instance = MockScraper.return_value
            mock_instance.scrape_zoning_chapter = AsyncMock(side_effect=mock_scrape)

            results = await ingest_all()

        assert len(results) == 2
        assert results["good_city"] == 0
        assert results["bad_city"] == 0
