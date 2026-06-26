"""Retrieve ordinance data for the missing Broward + Miami-Dade municipalities.

Paces discovery against the Municode Library API (rate-limited at 429 if hammered)
then ingests each city via the native MunicodeScraper (api.municode.com, returns
raw HTML — tables preserved) -> chunk_sections (_table_to_text) -> ordinance_chunks.

Run (background; paced to avoid 429s):
    uv run python scripts/retrieve_missing_ordinances.py
    uv run python scripts/retrieve_missing_ordinances.py --dry-run   # show plan only
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from plotlot.ingestion.discovery import discover_municode_authority_for_name
from plotlot.pipeline.ingest import ingest_municipality

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("retrieve")

# The 36 missing/sparse municipalities from the gap audit (user-provided authoritative list).
MISSING_BROWARD = [
    "Coconut Creek", "Cooper City", "Dania Beach", "Hallandale Beach", "Lauderdale Lakes",
    "Lauderhill", "Lazy Lake", "Lighthouse Point", "Margate", "North Lauderdale",
    "Pembroke Park", "Pembroke Pines", "Plantation", "Sea Ranch Lakes", "Southwest Ranches",
    "Sunrise", "Tamarac", "West Park", "Weston", "Wilton Manors",
]
SPARSE_BROWARD = ["Hollywood", "Pompano Beach"]  # re-ingest (sparse chunks)

MISSING_MIAMI_DADE = [
    "Miami", "Florida City", "Coral Gables", "Golden Beach", "North Miami Beach",
    "Miami Shores", "Biscayne Park", "El Portal", "Indian Creek Village",
    "North Bay Village", "Bal Harbour", "Hialeah Gardens", "Medley", "Miami Lakes",
]
SPARSE_MIAMI_DADE = ["Opa-locka", "West Miami", "Pinecrest"]


async def retrieve_one(city: str, state: str, *, dry_run: bool) -> None:
    """Discover the municode config for a city, then ingest."""
    logger.info("=== %s, %s ===", city, state)
    try:
        config = await discover_municode_authority_for_name(city, state)
    except Exception as e:
        logger.warning("discovery failed for %s: %s", city, e)
        return
    if not config:
        logger.warning("no municode config found for %s, %s — may use a non-municode codifier", city, state)
        return
    logger.info("discovered %s: job_id=%s", city, config.job_id)
    if dry_run:
        logger.info("(dry-run) would ingest %s", city)
        return
    try:
        n = await ingest_municipality(config.municipality_key or city.lower().replace(" ", "_"), state=state)
        logger.info("ingested %s: %d chunks", city, n)
    except Exception as e:
        logger.error("ingest failed for %s: %s", city, e)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--delay", type=float, default=4.0,
                        help="seconds between discovery calls (avoid 429)")
    args = parser.parse_args()

    cities = [(c, "FL") for c in (MISSING_BROWARD + SPARSE_BROWARD + MISSING_MIAMI_DADE + SPARSE_MIAMI_DADE)]
    logger.info("Plan: retrieve %d municipalities (delay=%.1fs between discovery calls)",
                len(cities), args.delay)

    for i, (city, state) in enumerate(cities, 1):
        logger.info("[%d/%d] %s", i, len(cities), city)
        await retrieve_one(city, state, dry_run=args.dry_run)
        if i < len(cities):
            await asyncio.sleep(args.delay)

    logger.info("done.")


if __name__ == "__main__":
    asyncio.run(main())
