"""Municode API scraper for zoning ordinance text.

Fetches zoning chapter content from the Municode public REST API,
navigates the table-of-contents hierarchy, and returns raw HTML sections.

No authentication required — all endpoints are publicly accessible.
"""

import asyncio
import logging

import httpx

from plotlot.core.types import MunicodeConfig, RawSection, TocNode

logger = logging.getLogger(__name__)

BASE_URL = "https://api.municode.com"


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
        We find the matching doc by node_id and return its Content HTML.
        If no match, concatenate all doc Content fields.
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
            if docs:
                for doc in docs:
                    if doc.get("Id") == node_id:
                        title_html = doc.get("TitleHtml", "")
                        content = doc.get("Content", "")
                        return str(title_html) + str(content)

                parts = []
                for doc in docs:
                    title_html = doc.get("TitleHtml", "")
                    content = doc.get("Content", "")
                    if content:
                        parts.append(title_html + content)
                return "\n".join(parts)

            return str(data.get("Document", data.get("document", "")))
        return str(data)

    async def walk_toc(
        self,
        client: httpx.AsyncClient,
        config: MunicodeConfig,
        root_node_id: str,
        max_depth: int = 4,
    ) -> list[TocNode]:
        """Recursively walk the TOC tree from a root node, collecting leaf nodes."""
        all_leaves: list[TocNode] = []

        async def _recurse(node_id: str, depth: int, parent_heading: str | None):
            if depth > max_depth:
                return
            children = await self.get_toc_children(
                client, config, node_id=node_id, depth=depth, parent_heading=parent_heading
            )
            for child in children:
                if child.has_children:
                    await _recurse(child.node_id, depth + 1, child.heading)
                else:
                    all_leaves.append(child)

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
            leaves = await self.walk_toc(client, config, config.zoning_node_id, max_depth)
            logger.info("Found %d leaf sections for %s", len(leaves), config.municipality)

            for leaf in leaves:
                try:
                    html = await self.get_section_content(client, config, leaf.node_id)
                    if html:
                        sections.append(
                            RawSection(
                                municipality=config.municipality,
                                county=config.county,
                                node_id=leaf.node_id,
                                heading=leaf.heading,
                                parent_heading=leaf.parent_heading,
                                html_content=html,
                                depth=leaf.depth,
                            )
                        )
                except Exception as e:
                    logger.warning(
                        "Failed to fetch %s (%s): %s",
                        leaf.node_id,
                        leaf.heading,
                        e,
                    )

        logger.info("Scraped %d sections for %s", len(sections), config.municipality)
        return sections
