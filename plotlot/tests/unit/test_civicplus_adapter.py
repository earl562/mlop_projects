"""Unit tests for the CivicPlus document-portal adapter.

All HTTP is mocked — these tests never touch ci.oceanside.ca.us.

Coverage:
  discover_civicplus_sources — link scraping, dedup, TOC skip, fetch failure
  _build_source              — article/suffix parsing, unique node ids
  make_zone_code_extractor   — bare district codes, noise rejection
  registry integration       — Oceanside resolves to a PDFAdapter
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from plotlot.ingestion.adapters.civicplus import (
    CivicPlusSite,
    _build_source,
    discover_civicplus_sources,
    make_zone_code_extractor,
)

INDEX_URL = "https://www.example-city.gov/planning/zoning-ordinance"

# Mirrors the real Oceanside markup: relative hrefs, a U+02D0 colon in the
# labels, a duplicate link, and a Table of Contents entry that must be skipped.
SAMPLE_HTML = """
<ul>
  <li><a href="/home/showpublisheddocument/4000/6379">Table of Contents</a></li>
  <li><a href="/home/showpublisheddocument/4008/6389" title="Click to download">
      Article 4ː Use Classifications</a></li>
  <li><a href="/home/showpublisheddocument/4010/6379">Article 4Aː Downtown Use Classifications</a></li>
  <li><a href="/home/showpublisheddocument/4012/6379">Article 10ː Residential Districts</a></li>
  <li><a href="/home/showpublisheddocument/4012/6379">Article 10ː Residential Districts</a></li>
  <li><a href="/home/showpublisheddocument/4014/6384">Article 10Cː Residential 'Coastal Zone'</a></li>
  <li><a href="/unrelated/page.html">Contact Planning</a></li>
</ul>
"""


def _client_returning(html: str, status: int = 200) -> httpx.AsyncClient:
    transport = httpx.MockTransport(lambda req: httpx.Response(status, text=html))
    return httpx.AsyncClient(transport=transport)


# ── discover_civicplus_sources ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_discovery_scrapes_documents_and_skips_toc() -> None:
    async with _client_returning(SAMPLE_HTML) as client:
        sources = await discover_civicplus_sources(INDEX_URL, client=client)

    # 5 unique doc links, minus the duplicate and minus Table of Contents.
    assert len(sources) == 4
    assert [s.section for s in sources] == ["Art.4", "Art.4A", "Art.10", "Art.10C"]
    assert all(s.url.startswith("https://www.example-city.gov/home/") for s in sources)


@pytest.mark.asyncio
async def test_discovery_ignores_non_document_links() -> None:
    async with _client_returning(SAMPLE_HTML) as client:
        sources = await discover_civicplus_sources(INDEX_URL, client=client)

    assert not any("unrelated" in s.url for s in sources)


@pytest.mark.asyncio
async def test_discovery_returns_empty_on_http_error() -> None:
    async with _client_returning("nope", status=503) as client:
        sources = await discover_civicplus_sources(INDEX_URL, client=client)

    assert sources == []


@pytest.mark.asyncio
async def test_discovery_returns_empty_on_transport_error() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dns failure", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(boom)) as client:
        assert await discover_civicplus_sources(INDEX_URL, client=client) == []


# ── _build_source ────────────────────────────────────────────────────────────


def test_build_source_parses_article_number_and_title() -> None:
    src = _build_source("https://x/doc", "Article 10ː Residential Districts", "Zoning")

    assert src.chapter == "Article 10 — Residential Districts"
    assert src.section == "Art.10"
    assert src.article == 10
    assert src.division == 0
    assert src.extra["designation"] == "10"


def test_build_source_encodes_suffix_into_division() -> None:
    """Suffixed articles must not collide with their base article's node id."""
    base = _build_source("https://x/a", "Article 10ː Residential Districts", "Zoning")
    coastal = _build_source("https://x/b", "Article 10Cː Residential Coastal", "Zoning")

    assert base.division == 0
    assert coastal.division == 3  # C -> 3
    assert (base.chapter_num, base.article, base.division) != (
        coastal.chapter_num,
        coastal.article,
        coastal.division,
    )


def test_build_source_accepts_ascii_colon() -> None:
    src = _build_source("https://x/doc", "Article 30: Site Regulations", "Zoning")
    assert src.section == "Art.30"
    assert src.chapter == "Article 30 — Site Regulations"


def test_build_source_keeps_unparseable_label_as_flat_document() -> None:
    src = _build_source("https://x/doc", "Zoning Map Amendments", "Comprehensive Zoning Ordinance")

    assert src.chapter == "Comprehensive Zoning Ordinance"
    assert src.section == "Zoning Map Amendments"
    assert src.article == 0


def test_build_source_never_emits_empty_section() -> None:
    """An empty `section` zeroes out citations downstream, so it must never happen."""
    for label in ["Article 10ː Residential", "Odd Document", "Chapter 3 - Definitions"]:
        assert _build_source("https://x/d", label, "Zoning").section.strip()


# ── make_zone_code_extractor ─────────────────────────────────────────────────


OCEANSIDE_CODES = ("RE", "RS", "RM", "RH", "RT", "CS", "CS-HO", "OS")


def test_extractor_finds_bare_district_codes() -> None:
    extract = make_zone_code_extractor(OCEANSIDE_CODES)
    codes = extract("The RS, RM, RH, and RT Districts permit dwellings.")

    assert set(codes) == {"RS", "RM", "RH", "RT"}


def test_extractor_is_case_sensitive() -> None:
    """Lowercase 'is'/'os' are prose; only uppercase are district codes."""
    extract = make_zone_code_extractor(("IS", "OS"))
    assert extract("the lot is within os limits") == []
    assert extract("the IS and OS districts") == ["IS", "OS"]


def test_extractor_matches_longest_code_first() -> None:
    extract = make_zone_code_extractor(OCEANSIDE_CODES)
    assert "CS-HO" in extract("Within the CS-HO District, hotels are permitted.")


def test_extractor_rejects_table_footnote_noise() -> None:
    """`L-7` is a footnote marker in Oceanside's tables, not a zoning district."""
    extract = make_zone_code_extractor(OCEANSIDE_CODES)
    codes = extract("Minimum lot area [L-7] and setbacks [L-33] apply in the RM District.")

    assert codes == ["RM"]


def test_extractor_keeps_numbered_variants_of_real_districts() -> None:
    extract = make_zone_code_extractor(OCEANSIDE_CODES)
    assert "RM-2" in extract("The RM-2 District allows multi-unit dwellings.")


def test_extractor_without_allowlist_falls_back_to_default() -> None:
    """Cities with no configured districts keep San Diego-style behaviour."""
    extract = make_zone_code_extractor(())
    assert extract("The RS-8 zone applies.") == ["RS-8"]


def test_extractor_prefers_density_suffixed_designator_over_bare_family() -> None:
    """Parcel records carry "RM-B"; matching only the bare "RM" would lose the boost."""
    extract = make_zone_code_extractor(("RM", "RM-A", "RM-B", "RM-C"))
    codes = extract("The RM-B District permits 10 to 15 units per acre.")

    assert "RM-B" in codes
    assert "RM" not in codes


def test_extractor_matches_coastal_zone_designators() -> None:
    """Coastal designators carry a slash ("R-1/CZ") and must survive escaping."""
    extract = make_zone_code_extractor(("RS", "R-1/CZ", "R-3/CZ"))
    codes = extract("Within the R-1/CZ District the coastal overlay applies.")

    assert codes == ["R-1/CZ"]


# ── Registry integration ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_oceanside_resolves_to_pdf_adapter_without_municode() -> None:
    """Oceanside must hit the PDF registry, never fall through to discovery."""
    from plotlot.ingestion.adapters.pdf import PDFAdapter
    from plotlot.ingestion.adapters.registry import resolve_adapter

    with (
        patch(
            "plotlot.ingestion.adapters.civicplus.discover_civicplus_sources",
            new=AsyncMock(return_value=[]),
        ) as disco,
        patch("plotlot.ingestion.adapters.registry._try_municode", new=AsyncMock()) as municode,
    ):
        adapter = await resolve_adapter("Oceanside", "CA", "San Diego")

    assert isinstance(adapter, PDFAdapter)
    assert adapter.municipality == "Oceanside"
    assert adapter.county == "San Diego"
    disco.assert_awaited_once()
    municode.assert_not_awaited()


def test_oceanside_site_is_registered() -> None:
    from plotlot.ingestion.adapters.civicplus import civicplus_site

    site = civicplus_site("oceanside", "ca")
    assert isinstance(site, CivicPlusSite)
    assert site.county == "San Diego"
    # Both the bare family (used in ordinance prose) and the density-suffixed
    # designator (used on the zoning map) must be present.
    assert {"RM", "RM-B", "RE-A", "RH-U", "R-1/CZ"} <= set(site.district_codes)
    # Single-letter districts are intentionally excluded as too noisy.
    assert not any(len(code) == 1 for code in site.district_codes)
