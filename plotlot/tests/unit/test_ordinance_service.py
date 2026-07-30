"""Tests for citation-rich ordinance service wrappers."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from plotlot.core.types import MunicodeConfig, TocNode
from plotlot.land_use.models import OrdinanceSearchArgs, OrdinanceJurisdiction
from plotlot.land_use.ordinances.service import _TOC_CACHE, search_municode_live


class _FakeScraper:
    async def walk_toc(self, client, config, root_node_id, max_depth=3):  # noqa: ANN001
        return [
            TocNode(
                node_id="parking-node",
                heading="Parking Requirements",
                has_children=False,
                depth=2,
                parent_heading="Development Standards",
            ),
            TocNode(
                node_id="sign-node",
                heading="Signs",
                has_children=False,
                depth=2,
                parent_heading="Development Standards",
            ),
        ]

    async def get_section_content(self, client, config, node_id):  # noqa: ANN001
        return "<p>Two parking spaces are required per dwelling unit.</p>"


class _FailingScraper:
    async def walk_toc(self, client, config, root_node_id, max_depth=3):  # noqa: ANN001
        request = httpx.Request("GET", "https://api.municode.com/codesToc/children")
        response = httpx.Response(404, request=request)
        raise httpx.HTTPStatusError("not found", request=request, response=response)


class _CountingScraper(_FakeScraper):
    walk_count = 0

    async def walk_toc(self, client, config, root_node_id, max_depth=3):  # noqa: ANN001
        type(self).walk_count += 1
        return await super().walk_toc(client, config, root_node_id, max_depth=max_depth)


@pytest.mark.asyncio
async def test_search_municode_live_uses_scraper_async_client_surface():
    config = MunicodeConfig(
        municipality="Charlotte",
        county="mecklenburg",
        client_id=1,
        product_id=2,
        job_id=3,
        zoning_node_id="root",
        state="NC",
    )

    with (
        patch(
            "plotlot.land_use.ordinances.service.get_municode_configs",
            new=AsyncMock(return_value={"charlotte": config}),
        ),
        patch("plotlot.land_use.ordinances.service.MunicodeScraper", _FakeScraper),
    ):
        results = await search_municode_live(
            OrdinanceSearchArgs(
                jurisdiction=OrdinanceJurisdiction(state="NC", municipality="Charlotte"),
                query="parking",
                limit=1,
            )
        )

    assert len(results) == 1
    assert results[0].heading == "Parking Requirements"
    assert "parking spaces" in results[0].snippet
    assert results[0].citation.jurisdiction == "Charlotte, NC"


@pytest.mark.asyncio
async def test_search_municode_live_caches_toc_walks_per_authority():
    _TOC_CACHE.clear()
    _CountingScraper.walk_count = 0
    config = MunicodeConfig(
        municipality="Charlotte",
        county="mecklenburg",
        client_id=1,
        product_id=2,
        job_id=3,
        zoning_node_id="root",
        state="NC",
    )

    with (
        patch(
            "plotlot.land_use.ordinances.service.get_municode_configs",
            new=AsyncMock(return_value={"charlotte": config}),
        ),
        patch("plotlot.land_use.ordinances.service.MunicodeScraper", _CountingScraper),
    ):
        first = await search_municode_live(
            OrdinanceSearchArgs(
                jurisdiction=OrdinanceJurisdiction(state="NC", municipality="Charlotte"),
                query="parking",
                limit=1,
            )
        )
        second = await search_municode_live(
            OrdinanceSearchArgs(
                jurisdiction=OrdinanceJurisdiction(state="NC", municipality="Charlotte"),
                query="sign",
                limit=1,
            )
        )

    assert len(first) == 1
    assert len(second) == 1
    assert _CountingScraper.walk_count == 1


@pytest.mark.asyncio
async def test_search_municode_live_returns_empty_for_stale_upstream_node():
    config = MunicodeConfig(
        municipality="Charlotte",
        county="mecklenburg",
        client_id=1,
        product_id=2,
        job_id=3,
        zoning_node_id="stale",
        state="NC",
    )

    with (
        patch(
            "plotlot.land_use.ordinances.service.get_municode_configs",
            new=AsyncMock(return_value={"charlotte": config}),
        ),
        patch("plotlot.land_use.ordinances.service.MunicodeScraper", _FailingScraper),
    ):
        results = await search_municode_live(
            OrdinanceSearchArgs(
                jurisdiction=OrdinanceJurisdiction(state="NC", municipality="Charlotte"),
                query="parking",
                limit=1,
            )
        )

    assert results == []


@pytest.mark.asyncio
async def test_search_municode_live_discovers_authority_when_cache_is_empty():
    config = MunicodeConfig(
        municipality="Miami Gardens",
        county="miami-dade",
        client_id=11,
        product_id=22,
        job_id=33,
        zoning_node_id="root",
        state="FL",
    )

    with (
        patch(
            "plotlot.land_use.ordinances.service.get_municode_configs",
            new=AsyncMock(return_value={}),
        ),
        patch(
            "plotlot.land_use.ordinances.service.discover_municode_authority_for_name",
            new=AsyncMock(return_value=config),
        ) as discover_mock,
        patch("plotlot.land_use.ordinances.service.MunicodeScraper", _FakeScraper),
    ):
        results = await search_municode_live(
            OrdinanceSearchArgs(
                jurisdiction=OrdinanceJurisdiction(
                    state="FL",
                    municipality="Miami Gardens",
                    county="Miami-Dade",
                ),
                query="parking",
                limit=1,
            )
        )

    discover_mock.assert_awaited_once_with("Miami Gardens", "FL", county="Miami-Dade")
    assert len(results) == 1
    assert results[0].heading == "Parking Requirements"
    assert results[0].citation.jurisdiction == "Miami Gardens, FL"
