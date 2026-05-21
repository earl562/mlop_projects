"""Tests for non-Municode code-provider discovery."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from plotlot.land_use.code_providers import (
    _decode_duckduckgo_url,
    _is_source_candidate,
    discover_code_authorities,
    discover_openlegalcodes_authorities,
    platform_from_url,
)


def test_platform_from_url_identifies_known_hosts():
    assert platform_from_url("https://ecode360.com/AM4323") == "ecode360"
    assert (
        platform_from_url("https://codelibrary.amlegal.com/codes/foo/latest/overview") == "amlegal"
    )
    assert platform_from_url("https://www.codepublishing.com/CA/AlpineCounty/") == "codepublishing"
    assert platform_from_url("https://glenn.municipalcodeonline.com/") == "municipal_code_online"
    assert (
        platform_from_url("https://online.encodeplus.com/regs/guilfordcounty-nc/") == "encodeplus"
    )
    assert (
        platform_from_url("https://guilfordco-nc.elaws.us/code/do_land_development_ord") == "elaws"
    )
    assert platform_from_url("https://www.countyofglenn.net/planning") == "unknown"


def test_decode_duckduckgo_redirect_url():
    raw = "//duckduckgo.com/l/?uddg=https%3A%2F%2Fglenn.municipalcodeonline.com%2F&rut=abc"
    assert _decode_duckduckgo_url(raw) == "https://glenn.municipalcodeonline.com/"


def test_source_candidate_rejects_zoning_atlas_noise():
    assert not _is_source_candidate(
        "https://edit.zoningatlas.org/statsrollup/county/5855/",
        "Jones County, NC | National Zoning Atlas Editor",
        "Jones",
        "NC",
    )


@pytest.mark.asyncio
async def test_discover_openlegalcodes_authorities_filters_exact_county():
    async def fake_jurisdictions(state):  # noqa: ANN001
        return [
            {
                "id": "ca-alpine-county",
                "name": "Alpine County, CA",
                "type": "county",
                "state": "CA",
                "publisher": "codepublishing",
                "sourceUrl": "https://www.codepublishing.com/CA/AlpineCounty/",
                "status": "available",
            },
            {
                "id": "ca-alpine",
                "name": "Alpine, CA",
                "type": "city",
                "state": "CA",
                "publisher": "municode",
                "sourceUrl": "https://library.municode.com/ca/alpine/codes/code_of_ordinances",
                "status": "available",
            },
        ]

    with patch(
        "plotlot.land_use.code_providers._openlegalcodes_jurisdictions",
        new=fake_jurisdictions,
    ):
        results = await discover_openlegalcodes_authorities(county="Alpine", state="CA")

    assert len(results) == 1
    assert results[0].jurisdiction_id == "ca-alpine-county"
    assert results[0].platform == "codepublishing"
    assert results[0].confidence == "high"


@pytest.mark.asyncio
async def test_discover_code_authorities_uses_web_fallback_when_olc_missing():
    html = """
    <a rel="nofollow" class="result__a"
       href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fglenn.municipalcodeonline.com%2F&amp;rut=x">
       Municipal Code Online - Glenn County</a>
    """

    async def fake_jurisdictions(state):  # noqa: ANN001
        return []

    async def fake_get(self, url, params=None):  # noqa: ANN001
        request = httpx.Request("GET", url)
        if "elaws.us" in str(url):
            return httpx.Response(404, request=request)
        return httpx.Response(200, text=html, request=request)

    with (
        patch(
            "plotlot.land_use.code_providers._openlegalcodes_jurisdictions",
            new=fake_jurisdictions,
        ),
        patch("plotlot.land_use.code_providers.httpx.AsyncClient.get", new=fake_get),
    ):
        results = await discover_code_authorities(county="Glenn", state="CA")

    assert len(results) == 1
    assert results[0].platform == "municipal_code_online"
    assert results[0].source_url == "https://glenn.municipalcodeonline.com/"


@pytest.mark.asyncio
async def test_discover_code_authorities_prefers_hosted_code_to_official_page():
    html = """
    <a rel="nofollow" class="result__a" href="https://www.guilfordcountync.gov/services/planning">
       Guilford County Planning and Development</a>
    <a rel="nofollow" class="result__a" href="https://online.encodeplus.com/regs/guilfordcounty-nc/">
       Guilford County, NC Unified Development Ordinance</a>
    """

    async def fake_jurisdictions(state):  # noqa: ANN001
        return []

    async def fake_get(self, url, params=None):  # noqa: ANN001
        request = httpx.Request("GET", url)
        if "municipalcodeonline.com" in str(url) or "elaws.us" in str(url):
            return httpx.Response(404, request=request)
        return httpx.Response(200, text=html, request=request)

    with (
        patch(
            "plotlot.land_use.code_providers._openlegalcodes_jurisdictions",
            new=fake_jurisdictions,
        ),
        patch("plotlot.land_use.code_providers.httpx.AsyncClient.get", new=fake_get),
    ):
        results = await discover_code_authorities(county="Guilford", state="NC")

    assert len(results) == 2
    assert results[0].platform == "encodeplus"
    assert results[1].platform == "official_county_site"
