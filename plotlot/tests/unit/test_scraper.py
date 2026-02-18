"""Tests for the Municode scraper module."""

import pytest

from plotlot.core.types import (
    MUNICODE_CONFIGS,
    RawSection,
    TocNode,
    _FALLBACK_CONFIGS,
)
from plotlot.ingestion.scraper import BASE_URL, MunicodeScraper


class TestMunicodeConfig:
    def test_miami_dade_config(self):
        config = MUNICODE_CONFIGS["miami_dade"]
        assert config.municipality == "Unincorporated Miami-Dade"
        assert config.county == "miami_dade"
        assert config.client_id == 11719
        assert config.product_id == 10620

    def test_fort_lauderdale_config(self):
        config = MUNICODE_CONFIGS["fort_lauderdale"]
        assert config.municipality == "Fort Lauderdale"
        assert config.county == "broward"

    def test_fallback_configs_alias(self):
        assert MUNICODE_CONFIGS is _FALLBACK_CONFIGS


class TestRawSection:
    def test_raw_section_creation(self):
        section = RawSection(
            municipality="Miami",
            county="miami_dade",
            node_id="NODE123",
            heading="Sec. 33-49. - Minimum lot requirements",
            parent_heading="Chapter 33",
            html_content="<p>Content here</p>",
            depth=2,
        )
        assert section.municipality == "Miami"
        assert section.node_id == "NODE123"
        assert section.depth == 2


class TestTocNode:
    def test_toc_node_creation(self):
        node = TocNode(
            node_id="NODE1",
            heading="Article 1 - General",
            has_children=True,
            depth=1,
        )
        assert node.node_id == "NODE1"
        assert node.has_children is True
        assert node.children == []

    def test_toc_node_with_parent(self):
        node = TocNode(
            node_id="NODE2",
            heading="Sec. 33-49",
            has_children=False,
            depth=2,
            parent_heading="Chapter 33",
        )
        assert node.parent_heading == "Chapter 33"


class TestMunicodeScraper:
    def test_scraper_init(self):
        scraper = MunicodeScraper()
        assert scraper._semaphore._value == 5

    def test_scraper_custom_concurrency(self):
        scraper = MunicodeScraper(max_concurrent=3)
        assert scraper._semaphore._value == 3

    @pytest.mark.asyncio
    async def test_get_toc_children_mock(self):
        import httpx

        class MockAsyncClient:
            async def get(self, url, params=None):
                request = httpx.Request("GET", url)
                return httpx.Response(
                    200,
                    json=[
                        {"Id": "NODE1", "Heading": "Article 1", "HasChildren": True},
                        {"Id": "NODE2", "Heading": "Sec. 33-1", "HasChildren": False},
                    ],
                    request=request,
                )

        scraper = MunicodeScraper()
        config = MUNICODE_CONFIGS["miami_dade"]
        client = MockAsyncClient()

        nodes = await scraper.get_toc_children(client, config, node_id="ROOT")
        assert len(nodes) == 2
        assert nodes[0].node_id == "NODE1"
        assert nodes[0].has_children is True

    @pytest.mark.asyncio
    async def test_get_section_content_docs_format(self):
        import httpx

        class MockAsyncClient:
            async def get(self, url, params=None):
                request = httpx.Request("GET", url)
                return httpx.Response(
                    200,
                    json={
                        "Docs": [
                            {
                                "Id": "NODE1",
                                "TitleHtml": "<h3>Sec. 33-49</h3>",
                                "Content": "<p>Minimum lot width is 75 feet.</p>",
                            }
                        ]
                    },
                    request=request,
                )

        scraper = MunicodeScraper()
        config = MUNICODE_CONFIGS["miami_dade"]
        client = MockAsyncClient()

        html = await scraper.get_section_content(client, config, "NODE1")
        assert "75 feet" in html
        assert "<h3>" in html

    @pytest.mark.asyncio
    async def test_get_section_content_legacy_format(self):
        import httpx

        class MockAsyncClient:
            async def get(self, url, params=None):
                request = httpx.Request("GET", url)
                return httpx.Response(
                    200,
                    json={"Document": "<p>Legacy content.</p>"},
                    request=request,
                )

        scraper = MunicodeScraper()
        config = MUNICODE_CONFIGS["miami_dade"]
        client = MockAsyncClient()

        html = await scraper.get_section_content(client, config, "NODE1")
        assert "Legacy content" in html

    @pytest.mark.asyncio
    async def test_get_section_content_empty(self):
        import httpx

        class MockAsyncClient:
            async def get(self, url, params=None):
                request = httpx.Request("GET", url)
                return httpx.Response(200, json={"Document": ""}, request=request)

        scraper = MunicodeScraper()
        config = MUNICODE_CONFIGS["fort_lauderdale"]
        client = MockAsyncClient()

        html = await scraper.get_section_content(client, config, "NODE1")
        assert html == ""


class TestConstants:
    def test_base_url(self):
        assert BASE_URL == "https://api.municode.com"

    def test_fallback_configs_count(self):
        assert len(_FALLBACK_CONFIGS) == 2

    def test_municode_configs_count(self):
        assert len(MUNICODE_CONFIGS) == 2
