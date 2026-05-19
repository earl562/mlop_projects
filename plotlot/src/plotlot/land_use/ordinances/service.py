"""Ordinance service wrapper that returns citation-rich results."""

from __future__ import annotations

import re

import httpx

from plotlot.ingestion.discovery import (
    discover_municode_authority_for_name,
    get_municode_configs,
    resolve_municode_config,
)
from plotlot.core.types import TocNode
from plotlot.ingestion.scraper import MunicodeScraper
from plotlot.land_use.citations import ordinance_citation
from plotlot.land_use.models import OrdinanceSearchArgs, OrdinanceSearchResult

_TOC_CACHE: dict[tuple[int, int, str], list[TocNode]] = {}


async def search_municode_live(args: OrdinanceSearchArgs) -> list[OrdinanceSearchResult]:
    """Search Municode for ordinance sections and return cited results."""

    configs = await get_municode_configs()
    muni_key = args.jurisdiction.municipality or args.jurisdiction.county or ""
    state = args.jurisdiction.state or None
    config = resolve_municode_config(configs, muni_key, state=state)
    if config is None and state and muni_key:
        config = await discover_municode_authority_for_name(
            muni_key,
            state,
            county=args.jurisdiction.county,
        )
    if config is None:
        return []

    scraper = MunicodeScraper()
    raw_terms = [term.lower() for term in re.findall(r"[a-z0-9-]+", args.query) if len(term) >= 3]
    query_terms: list[str] = []
    for term in raw_terms:
        query_terms.append(term)
        if term.endswith("s") and len(term) > 3:
            query_terms.append(term[:-1])

    async with httpx.AsyncClient(timeout=20.0) as client:
        cache_key = (config.product_id, config.job_id, config.zoning_node_id)
        nodes = _TOC_CACHE.get(cache_key)
        if nodes is None:
            try:
                nodes = await scraper.walk_toc(client, config, config.zoning_node_id, max_depth=3)
            except httpx.HTTPError:
                return []
            _TOC_CACHE[cache_key] = nodes

        ranked = []
        for node in nodes:
            haystack = f"{node.heading or ''} {node.parent_heading or ''}".lower()
            score = sum(1 for term in query_terms if term in haystack)
            if score > 0:
                ranked.append((score, node))
        ranked.sort(key=lambda item: item[0], reverse=True)

        results: list[OrdinanceSearchResult] = []
        for _, node in ranked[: args.limit]:
            heading = node.heading or ""
            parent = node.parent_heading or ""
            try:
                html = await scraper.get_section_content(client, config, node.node_id)
            except httpx.HTTPError:
                continue
            snippet = (html or "").replace("\n", " ")
            snippet = snippet[:300].strip() or heading
            url = f"https://api.municode.com/codescontent?nodeId={node.node_id}"
            citation = ordinance_citation(
                title=heading or "Ordinance section",
                url=url,
                jurisdiction=args.jurisdiction.label(),
                path=[p for p in [parent, heading] if p],
                raw_text_for_hash=f"{config.municipality}:{node.node_id}:{heading}:{snippet}",
            )
            results.append(
                OrdinanceSearchResult(
                    section_id=node.node_id,
                    heading=heading or "Ordinance section",
                    path=[p for p in [parent] if p],
                    snippet=snippet or heading or "",
                    citation=citation,
                )
            )

        return results
