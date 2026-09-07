"""Municode API adapter.

Wraps the existing MunicodeScraper + chunk_sections pipeline behind the
SourceAdapter interface.  Any municipality discoverable on Municode gets
coverage through this adapter with zero per-municipality code.
"""

from __future__ import annotations

import logging

from plotlot.core.types import MunicodeConfig, TextChunk
from plotlot.ingestion.adapters.base import SourceAdapter
from plotlot.ingestion.chunker import chunk_sections
from plotlot.ingestion.scraper import MunicodeScraper

logger = logging.getLogger(__name__)


class MunicodeAdapter(SourceAdapter):
    """Fetches zoning ordinances from the Municode REST API.

    Delegates scraping to MunicodeScraper (rate-limited, concurrent fetch)
    and chunking to chunk_sections (HTML → overlapping TextChunks).
    """

    name = "municode"

    def __init__(self, config: MunicodeConfig) -> None:
        super().__init__(config.municipality, config.county, config.state)
        self.config = config

    async def fetch_chunks(self) -> list[TextChunk]:
        scraper = MunicodeScraper()
        sections = await scraper.scrape_zoning_chapter(self.config)
        chunks = chunk_sections(sections)
        logger.info(
            "municode_adapter_done municipality=%s chunks=%d",
            self.municipality,
            len(chunks),
        )
        return chunks
