"""Abstract base for all ingestion source adapters.

Every concrete adapter scrapes one type of zoning source (Municode REST API,
PDF files, raw HTML) and returns list[TextChunk] — the common currency fed
into the embedding pipeline.  New source type = new subclass here, no new
pipeline file.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import ClassVar

from plotlot.core.types import TextChunk

logger = logging.getLogger(__name__)


class SourceAdapter(ABC):
    """Scrapes a municipality's zoning ordinance and returns text chunks.

    Subclasses implement fetch_chunks() to handle source-specific scraping
    and chunking, then return a flat list[TextChunk] regardless of source.
    """

    name: ClassVar[str]

    def __init__(self, municipality: str, county: str, state: str) -> None:
        self.municipality = municipality
        self.county = county
        self.state = state

    @abstractmethod
    async def fetch_chunks(self) -> list[TextChunk]:
        """Scrape and chunk the ordinance. Returns chunks ready for embedding."""
        ...

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.municipality!r}, {self.state!r})"
