"""Tests for Tier-1 codifier platform discovery + WebCodifierAdapter.

All transport calls are mocked — no live HTTP, no Jina quota usage.

Context: cities not on Municode (e.g. 7 of San Diego County's 18) sit on
codifier platforms (Code Publishing, eCode360, municipal.codes, American
Legal) that are Cloudflare-walled to plain HTTP clients. Discovery probes
their predictable URL patterns through a direct-then-Jina transport; the
generic WebCodifierAdapter walks the TOC and chunks zoning pages.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from plotlot.core.errors import NoAdapterError
from plotlot.ingestion.adapters.codifier import (
    CodifierHit,
    PageContent,
    WebCodifierAdapter,
    _parse_jina_page,
    _resolve_spa_fragment,
    codifier_url_patterns,
    discover_codifier,
)
from plotlot.ingestion.adapters.registry import resolve_adapter

# ---------------------------------------------------------------------------
# URL pattern generation
# ---------------------------------------------------------------------------


def test_url_patterns_cover_known_platforms() -> None:
    pats = dict[str, list[str]]()
    for platform, url in codifier_url_patterns("Chula Vista", "ca"):
        pats.setdefault(platform, []).append(url)

    assert pats["codepublishing"] == ["https://www.codepublishing.com/CA/ChulaVista/"]
    assert pats["municipal.codes"] == ["https://chulavista.municipal.codes/"]
    assert pats["ecode360"] == ["https://resolve.ecode360.com/codes/chulavista"]
    # Multi-word cities probe both amlegal slug conventions
    assert "https://codelibrary.amlegal.com/codes/chulavista/latest/overview" in pats["amlegal"]
    assert "https://codelibrary.amlegal.com/codes/chula_vista/latest/overview" in pats["amlegal"]


def test_url_patterns_single_word_city_has_one_amlegal_variant() -> None:
    pats = [p for p, _ in codifier_url_patterns("Poway", "CA")]
    assert pats.count("amlegal") == 1


# ---------------------------------------------------------------------------
# Jina Reader envelope parsing
# ---------------------------------------------------------------------------

_JINA_404 = """Title: Page Not Found | General Code

URL Source: https://www.codepublishing.com/CA/Santee/

Warning: Target URL returned error 404: Not Found

Markdown Content:
That page does not seem to exist.
"""

_JINA_HIT = """Title: Chula Vista Municipal Code

URL Source: https://www.codepublishing.com/CA/ChulaVista/

Markdown Content:
[Title 17 SUBDIVISIONS](https://www.codepublishing.com/CA/ChulaVista/#!/ChulaVista17.html)
[Title 19 ZONING](https://www.codepublishing.com/CA/ChulaVista/#!/ChulaVista19.html)
[Business Licenses](https://www.codepublishing.com/CA/ChulaVista/#!/ChulaVista05.html)
"""


def test_parse_jina_404_envelope() -> None:
    page = _parse_jina_page(_JINA_404, "https://www.codepublishing.com/CA/Santee/")
    assert page.target_status == 404
    assert page.title == "Page Not Found | General Code"


def test_parse_jina_hit_envelope_extracts_links_and_title() -> None:
    page = _parse_jina_page(_JINA_HIT, "https://www.codepublishing.com/CA/ChulaVista/")
    assert page.target_status == 200
    assert page.title == "Chula Vista Municipal Code"
    assert page.final_url == "https://www.codepublishing.com/CA/ChulaVista/"
    labels = [label for label, _ in page.links]
    assert "Title 19 ZONING" in labels


def test_parse_jina_challenge_marks_blocked() -> None:
    body = "Title: x\n\nURL Source: https://a/\n\nMarkdown Content:\nJust a moment..."
    page = _parse_jina_page(body, "https://a/")
    assert page.blocked is True


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


class _FakeTransport:
    """Maps URL → PageContent; records what was fetched."""

    def __init__(self, responses: dict[str, PageContent]) -> None:
        self.responses = responses
        self.fetched: list[str] = []

    async def fetch(self, url: str) -> PageContent:
        self.fetched.append(url)
        return self.responses.get(
            url, PageContent(target_status=404, text="", title="", final_url=url)
        )


def _page(status: int, text: str = "", title: str = "", url: str = "", links=None) -> PageContent:
    return PageContent(
        target_status=status, text=text, title=title, final_url=url, links=links or []
    )


@pytest.mark.asyncio
async def test_discover_returns_first_hit_platform() -> None:
    """El Cajon pattern: 404 on codepublishing/municipal.codes, hit on ecode360."""
    transport = _FakeTransport(
        {
            "https://resolve.ecode360.com/codes/elcajon": _page(
                200,
                text="City of El Cajon code of ordinances",
                title="City of El Cajon, CA Code",
                url="https://ecode360.com/EL1234",
            ),
        }
    )
    hit = await discover_codifier("El Cajon", "CA", transport=transport)  # type: ignore[arg-type]

    assert hit is not None
    assert hit.platform == "ecode360"
    assert hit.final_url == "https://ecode360.com/EL1234"
    # Earlier platforms were probed and rejected before the hit
    assert "https://www.codepublishing.com/CA/ElCajon/" in transport.fetched


@pytest.mark.asyncio
async def test_discover_rejects_soft_404_without_city_mention() -> None:
    """A 200 page that never mentions the city must not count as a hit."""
    transport = _FakeTransport(
        {
            "https://www.codepublishing.com/CA/Santee/": _page(
                200, text="Welcome to General Code's library", title="General Code", url="x"
            ),
        }
    )
    hit = await discover_codifier("Santee", "CA", transport=transport)  # type: ignore[arg-type]
    assert hit is None


@pytest.mark.asyncio
async def test_discover_all_miss_returns_none() -> None:
    transport = _FakeTransport({})
    hit = await discover_codifier("Zzyzxville", "CA", transport=transport)  # type: ignore[arg-type]
    assert hit is None


@pytest.mark.asyncio
async def test_discover_empty_inputs_short_circuit() -> None:
    transport = _FakeTransport({})
    assert await discover_codifier("", "CA", transport=transport) is None  # type: ignore[arg-type]
    assert await discover_codifier("Poway", "", transport=transport) is None  # type: ignore[arg-type]
    assert transport.fetched == []


# ---------------------------------------------------------------------------
# WebCodifierAdapter walk
# ---------------------------------------------------------------------------

_ROOT = "https://www.codepublishing.com/CA/Poway/"
# Root TOC links are SPA fragments; the adapter rewrites them to real /html/
# content paths before fetching (the fragment never reaches the server).
_ZONING_FRAGMENT = f"{_ROOT}#!/Poway17/Poway17.html"
_ZONING_URL = f"{_ROOT}html/Poway17/Poway17.html"
_OTHER_FRAGMENT = f"{_ROOT}#!/Poway05/Poway05.html"
_OTHER_URL = f"{_ROOT}html/Poway05/Poway05.html"
_SEC_URL = f"{_ROOT}html/Poway17/Poway1704.html"
_LONG = "Setbacks shall be twenty feet in the R-1 zone. " * 20
_LONG2 = "Maximum building height shall be thirty-five feet. " * 20


def _poway_responses() -> dict[str, PageContent]:
    return {
        _ROOT: _page(
            200,
            text="Poway Municipal Code",
            title="Poway Municipal Code",
            url=_ROOT,
            links=[
                ("Title 17 ZONING", _ZONING_FRAGMENT),
                ("Business Licenses", _OTHER_FRAGMENT),
                ("External", "https://www.generalcode.com/library/"),
            ],
        ),
        _ZONING_URL: _page(
            200,
            text=_LONG,
            title="Title 17 ZONING",
            url=_ZONING_URL,
            links=[("17.04 Definitions", _SEC_URL)],
        ),
        _SEC_URL: _page(200, text=_LONG2, title="17.04 Definitions", url=_SEC_URL),
    }


def _hit() -> CodifierHit:
    return CodifierHit(
        platform="codepublishing", url=_ROOT, final_url=_ROOT, title="Poway Municipal Code"
    )


@pytest.mark.asyncio
async def test_adapter_walks_zoning_links_and_chunks() -> None:
    transport = _FakeTransport(_poway_responses())
    adapter = WebCodifierAdapter("Poway", "San Diego", "CA", hit=_hit())

    with patch("plotlot.ingestion.adapters.codifier.CodifierTransport", return_value=transport):
        chunks = await adapter.fetch_chunks()

    assert chunks, "expected chunks from zoning pages"
    # SPA fragments were rewritten to real /html/ paths before fetching;
    # followed the zoning title and its numbered child — not Business Licenses,
    # not the off-host General Code link.
    assert _ZONING_URL in transport.fetched
    assert _SEC_URL in transport.fetched
    assert _ZONING_FRAGMENT not in transport.fetched
    assert _OTHER_URL not in transport.fetched
    assert _OTHER_FRAGMENT not in transport.fetched
    assert "https://www.generalcode.com/library/" not in transport.fetched

    meta = chunks[0].metadata
    assert meta.municipality == "Poway"
    assert meta.county == "San Diego"
    assert meta.chapter == "Title 17 ZONING"
    assert meta.municode_node_id.startswith("web_")
    # Stable node IDs → idempotent upserts on re-ingest
    rerun_transport = _FakeTransport(_poway_responses())
    with patch(
        "plotlot.ingestion.adapters.codifier.CodifierTransport", return_value=rerun_transport
    ):
        rerun_chunks = await WebCodifierAdapter(
            "Poway", "San Diego", "CA", hit=_hit()
        ).fetch_chunks()
    assert [c.metadata.municode_node_id for c in rerun_chunks] == [
        c.metadata.municode_node_id for c in chunks
    ]


@pytest.mark.asyncio
async def test_adapter_respects_max_pages_cap() -> None:
    responses = _poway_responses()
    transport = _FakeTransport(responses)
    adapter = WebCodifierAdapter("Poway", "San Diego", "CA", hit=_hit(), max_pages=1)

    with patch("plotlot.ingestion.adapters.codifier.CodifierTransport", return_value=transport):
        await adapter.fetch_chunks()

    # root + 1 page max (root fetch is not counted against the cap)
    assert transport.fetched.count(_SEC_URL) == 0


@pytest.mark.asyncio
async def test_adapter_blocked_root_returns_empty() -> None:
    transport = _FakeTransport(
        {_ROOT: PageContent(target_status=403, text="", title="", final_url=_ROOT, blocked=True)}
    )
    adapter = WebCodifierAdapter("Poway", "San Diego", "CA", hit=_hit())
    with patch("plotlot.ingestion.adapters.codifier.CodifierTransport", return_value=transport):
        chunks = await adapter.fetch_chunks()
    assert chunks == []


@pytest.mark.asyncio
async def test_adapter_numbered_toc_fallback() -> None:
    """TOCs with no keyword labels (e.g. 'Title 19') still get walked."""
    responses = {
        _ROOT: _page(
            200,
            text="Poway",
            title="Poway Municipal Code",
            url=_ROOT,
            links=[("Chapter 17.08 Residential Zones", _SEC_URL)],
        ),
        _SEC_URL: _page(200, text=_LONG, title="Chapter 17.08", url=_SEC_URL),
    }
    transport = _FakeTransport(responses)
    adapter = WebCodifierAdapter("Poway", "San Diego", "CA", hit=_hit())
    with patch("plotlot.ingestion.adapters.codifier.CodifierTransport", return_value=transport):
        chunks = await adapter.fetch_chunks()
    assert chunks
    assert _SEC_URL in transport.fetched


# ---------------------------------------------------------------------------
# Regressions from the live Poway smoke test (CardinalityViolation + shell text)
# ---------------------------------------------------------------------------


def test_resolve_spa_fragment_rewrites_codepublishing_links() -> None:
    """#!/X/Y.html fragments → real /html/X/Y.html content paths."""
    assert (
        _resolve_spa_fragment("https://www.codepublishing.com/CA/Poway/#!/Poway17/Poway17.html")
        == "https://www.codepublishing.com/CA/Poway/html/Poway17/Poway17.html"
    )
    # Non-SPA URLs pass through untouched
    assert _resolve_spa_fragment("https://ecode360.com/EL1234") == "https://ecode360.com/EL1234"
    assert (
        _resolve_spa_fragment("https://a.com/page.html#17.08.010")
        == "https://a.com/page.html#17.08.010"
    )


@pytest.mark.asyncio
async def test_adapter_skips_spa_shell_duplicate_content() -> None:
    """Pages that serve the same landing-shell text must produce NO chunks and
    NO colliding node IDs (live failure: CardinalityViolation on upsert)."""
    shell = "Poway Municipal Code fuzzy searching will find a word " * 10
    responses = {
        _ROOT: _page(
            200,
            text=shell,
            title="Poway Municipal Code",
            url=_ROOT,
            links=[
                ("Title 16 LAND USE", f"{_ROOT}#!/Poway16/Poway16.html"),
                ("Title 17 ZONING", f"{_ROOT}#!/Poway17/Poway17.html"),
            ],
        ),
        # Both rewritten URLs return the SAME shell text (fragment SPA behavior)
        f"{_ROOT}html/Poway16/Poway16.html": _page(200, text=shell, url=_ROOT),
        f"{_ROOT}html/Poway17/Poway17.html": _page(200, text=shell, url=_ROOT),
    }
    transport = _FakeTransport(responses)
    adapter = WebCodifierAdapter("Poway", "San Diego", "CA", hit=_hit())
    with patch("plotlot.ingestion.adapters.codifier.CodifierTransport", return_value=transport):
        chunks = await adapter.fetch_chunks()

    assert chunks == [], "shell/duplicate content must not be chunked"


@pytest.mark.asyncio
async def test_adapter_node_ids_unique_across_pages() -> None:
    """Distinct pages must never share a (node_id, chunk_index) pair — the
    upsert key. Even if final URLs collide, content-hash suffixing keeps them
    apart."""
    responses = {
        _ROOT: _page(
            200,
            text="Poway Municipal Code",
            title="Poway Municipal Code",
            url=_ROOT,
            links=[
                ("Title 16 LAND USE", f"{_ROOT}#!/Poway16/Poway16.html"),
                ("Title 17 ZONING", f"{_ROOT}#!/Poway17/Poway17.html"),
            ],
        ),
        f"{_ROOT}html/Poway16/Poway16.html": _page(200, text=_LONG, url=_ROOT),
        f"{_ROOT}html/Poway17/Poway17.html": _page(200, text=_LONG2, url=_ROOT),
    }
    transport = _FakeTransport(responses)
    adapter = WebCodifierAdapter("Poway", "San Diego", "CA", hit=_hit())
    with patch("plotlot.ingestion.adapters.codifier.CodifierTransport", return_value=transport):
        chunks = await adapter.fetch_chunks()

    keys = [(c.metadata.municode_node_id, c.metadata.chunk_index) for c in chunks]
    assert len(keys) == len(set(keys)), f"duplicate upsert keys: {keys}"


@pytest.mark.asyncio
async def test_adapter_does_not_fetch_in_page_anchors() -> None:
    """Child links that are anchors into the same document burn quota for
    duplicate content — they must be skipped without fetching."""
    responses = {
        _ROOT: _page(
            200,
            text="Poway Municipal Code",
            title="Poway Municipal Code",
            url=_ROOT,
            links=[("Title 17 ZONING", _ZONING_URL)],
        ),
        _ZONING_URL: _page(
            200,
            text=_LONG,
            title="Title 17",
            url=_ZONING_URL,
            links=[
                ("17.08.010 Purposes.", f"{_ZONING_URL}#17.08.010"),
                ("17.08.020 Zones.", f"{_ZONING_URL}#17.08.020"),
            ],
        ),
    }
    transport = _FakeTransport(responses)
    adapter = WebCodifierAdapter("Poway", "San Diego", "CA", hit=_hit())
    with patch("plotlot.ingestion.adapters.codifier.CodifierTransport", return_value=transport):
        chunks = await adapter.fetch_chunks()

    assert chunks
    anchor_fetches = [u for u in transport.fetched if "#17.08" in u]
    assert anchor_fetches == [], f"in-page anchors were fetched: {anchor_fetches}"


# ---------------------------------------------------------------------------
# resolve_adapter wiring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_adapter_falls_back_to_codifier() -> None:
    """Municode miss + codifier hit → WebCodifierAdapter."""
    with (
        patch(
            "plotlot.ingestion.adapters.registry._try_municode",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "plotlot.ingestion.adapters.codifier.discover_codifier",
            new=AsyncMock(return_value=_hit()),
        ),
    ):
        adapter = await resolve_adapter("Poway", "CA", "San Diego")

    assert isinstance(adapter, WebCodifierAdapter)
    assert adapter.name == "codifier"
    assert adapter.municipality == "Poway"
    assert adapter.county == "San Diego"


@pytest.mark.asyncio
async def test_resolve_adapter_raises_when_all_tiers_miss() -> None:
    with (
        patch(
            "plotlot.ingestion.adapters.registry._try_municode",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "plotlot.ingestion.adapters.codifier.discover_codifier",
            new=AsyncMock(return_value=None),
        ),
        pytest.raises(NoAdapterError),
    ):
        await resolve_adapter("Zzyzxville", "CA")


@pytest.mark.asyncio
async def test_resolve_adapter_codifier_crash_degrades_to_no_adapter() -> None:
    """A codifier discovery crash must not propagate — honest NoAdapterError."""
    with (
        patch(
            "plotlot.ingestion.adapters.registry._try_municode",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "plotlot.ingestion.adapters.codifier.discover_codifier",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ),
        pytest.raises(NoAdapterError),
    ):
        await resolve_adapter("Poway", "CA")
