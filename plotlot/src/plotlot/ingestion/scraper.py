"""Municode API scraper for zoning ordinance text.

Fetches zoning chapter content from the Municode public REST API,
navigates the table-of-contents hierarchy, and returns raw HTML sections.

No authentication required — all endpoints are publicly accessible.
"""

import asyncio
import logging
from collections.abc import Coroutine, Iterable

import httpx
from bs4 import BeautifulSoup

from plotlot.core.types import MunicodeConfig, RawSection, TocNode
from plotlot.ingestion.source_acquisition import (
    SourceAcquisitionError,
    SourceFailureReason,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://api.municode.com"


async def _gather_owned[T](coroutines: Iterable[Coroutine[object, object, T]]) -> list[T]:
    tasks = [asyncio.create_task(coroutine) for coroutine in coroutines]
    try:
        return await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


class MunicodeScraper:
    """Async client for scraping zoning ordinances from the Municode API."""

    def __init__(self, max_concurrent: int = 5) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def _get(self, client: httpx.AsyncClient, path: str, **params) -> dict | list:
        """Rate-limited GET request to Municode API."""
        async with self._semaphore:
            url = f"{BASE_URL}/{path}"
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            return resp.json()  # type: ignore[no-any-return]

    async def get_toc_children(
        self,
        client: httpx.AsyncClient,
        config: MunicodeConfig,
        node_id: str | None = None,
        depth: int = 0,
        parent_heading: str | None = None,
    ) -> list[TocNode]:
        """Fetch children of a TOC node (or root if node_id is None)."""
        params: dict = {"jobId": config.job_id, "productId": config.product_id}
        if node_id:
            params["nodeId"] = node_id

        data = await self._get(client, "codesToc/children", **params)
        nodes = []
        for item in data:
            node = TocNode(
                node_id=item["Id"],
                heading=item.get("Heading", ""),
                has_children=item.get("HasChildren", False),
                depth=depth,
                parent_heading=parent_heading,
            )
            nodes.append(node)
        return nodes

    async def get_section_content(
        self,
        client: httpx.AsyncClient,
        config: MunicodeConfig,
        node_id: str,
    ) -> str:
        """Fetch the HTML content of a specific section.

        The Municode API returns {"Docs": [{"Id": ..., "Title": ..., "Content": ...}, ...]}.
        We find exactly one matching doc by node_id and return its Content HTML.
        """
        data = await self._get(
            client,
            "CodesContent",
            jobId=config.job_id,
            nodeId=node_id,
            productId=config.product_id,
        )
        if isinstance(data, dict):
            docs = data.get("Docs", [])
            if not isinstance(docs, list):
                raise SourceAcquisitionError(
                    f"{BASE_URL}/CodesContent",
                    SourceFailureReason.PARSE_ERROR,
                )
            if docs:
                matches: list[str] = []
                for doc in docs:
                    if not isinstance(doc, dict):
                        raise SourceAcquisitionError(
                            f"{BASE_URL}/CodesContent",
                            SourceFailureReason.PARSE_ERROR,
                        )
                    title_html = doc.get("TitleHtml", "")
                    content = doc.get("Content", "")
                    if not isinstance(title_html, str) or not isinstance(content, str):
                        raise SourceAcquisitionError(
                            f"{BASE_URL}/CodesContent",
                            SourceFailureReason.PARSE_ERROR,
                        )
                    if doc.get("Id") == node_id:
                        matches.append(title_html + content)
                if len(matches) != 1:
                    raise SourceAcquisitionError(
                        f"{BASE_URL}/CodesContent",
                        SourceFailureReason.IDENTITY_MISMATCH,
                    )
                return matches[0]

            document = data.get("Document", data.get("document", ""))
            if not isinstance(document, str):
                raise SourceAcquisitionError(
                    f"{BASE_URL}/CodesContent",
                    SourceFailureReason.PARSE_ERROR,
                )
            return document
        raise SourceAcquisitionError(
            f"{BASE_URL}/CodesContent",
            SourceFailureReason.PARSE_ERROR,
        )

    async def walk_toc(
        self,
        client: httpx.AsyncClient,
        config: MunicodeConfig,
        root_node_id: str,
        max_depth: int = 4,
    ) -> list[TocNode]:
        """Recursively walk the TOC tree from a root node, collecting leaf nodes."""
        all_leaves: list[TocNode] = []

        async def _recurse(node_id: str, depth: int, parent_heading: str | None) -> None:
            children = await self.get_toc_children(
                client, config, node_id=node_id, depth=depth, parent_heading=parent_heading
            )
            branches: list[TocNode] = []
            for child in children:
                if child.has_children:
                    if depth >= max_depth:
                        raise SourceAcquisitionError(
                            f"{BASE_URL}/codesToc/children",
                            SourceFailureReason.DEPTH_LIMIT,
                        )
                    branches.append(child)
                else:
                    all_leaves.append(child)
            if branches:
                await _gather_owned(
                    _recurse(child.node_id, depth + 1, child.heading) for child in branches
                )

        await _recurse(root_node_id, depth=1, parent_heading=None)
        return all_leaves

    async def scrape_zoning_chapter(
        self,
        config: MunicodeConfig,
        max_depth: int = 4,
    ) -> list[RawSection]:
        """Scrape all sections under a municipality's zoning chapter."""
        sections: list[RawSection] = []

        async with httpx.AsyncClient(timeout=30.0) as client:
            logger.info(
                "Walking TOC for %s (node: %s)",
                config.municipality,
                config.zoning_node_id,
            )
            try:
                leaves = await self.walk_toc(client, config, config.zoning_node_id, max_depth)
            except httpx.HTTPStatusError as exc:
                raise SourceAcquisitionError(
                    f"{BASE_URL}/codesToc/children",
                    SourceFailureReason.HTTP_ERROR,
                    exc.response.status_code,
                ) from exc
            except httpx.TransportError as exc:
                raise SourceAcquisitionError(
                    f"{BASE_URL}/codesToc/children",
                    SourceFailureReason.TRANSPORT_ERROR,
                ) from exc
            logger.info("Found %d leaf sections for %s", len(leaves), config.municipality)

            # Fetch all leaf sections in parallel (governed by self._semaphore)
            async def _fetch_leaf(leaf: TocNode) -> RawSection:
                try:
                    html = await self.get_section_content(client, config, leaf.node_id)
                except httpx.HTTPStatusError as exc:
                    raise SourceAcquisitionError(
                        f"{BASE_URL}/CodesContent",
                        SourceFailureReason.HTTP_ERROR,
                        exc.response.status_code,
                    ) from exc
                except httpx.TransportError as exc:
                    raise SourceAcquisitionError(
                        f"{BASE_URL}/CodesContent",
                        SourceFailureReason.TRANSPORT_ERROR,
                    ) from exc
                if not html or not BeautifulSoup(html, "html.parser").get_text(strip=True):
                    raise SourceAcquisitionError(
                        f"{BASE_URL}/CodesContent",
                        SourceFailureReason.EMPTY_CONTENT,
                    )
                return RawSection(
                    municipality=config.municipality,
                    county=config.county,
                    node_id=leaf.node_id,
                    heading=leaf.heading,
                    parent_heading=leaf.parent_heading,
                    html_content=html,
                    depth=leaf.depth,
                )

            results = await _gather_owned(_fetch_leaf(leaf) for leaf in leaves)
            sections = list(results)

        logger.info("Scraped %d sections for %s", len(sections), config.municipality)
        return sections
