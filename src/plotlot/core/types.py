"""Domain types for the plotlot zoning analysis platform.

All shared dataclasses and type definitions live here to prevent
circular imports and establish a single source of truth for the
domain model. Every other module imports from here.
"""

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Municode API types
# ---------------------------------------------------------------------------

@dataclass
class MunicodeConfig:
    """Municode API identifiers for a municipality's zoning code."""

    municipality: str
    county: str
    client_id: int
    product_id: int
    job_id: int
    zoning_node_id: str


@dataclass
class RawSection:
    """A raw section of ordinance text scraped from Municode."""

    municipality: str
    county: str
    node_id: str
    heading: str
    parent_heading: str | None
    html_content: str
    depth: int


@dataclass
class TocNode:
    """A node in the Municode table-of-contents tree."""

    node_id: str
    heading: str
    has_children: bool
    depth: int
    parent_heading: str | None = None
    children: list["TocNode"] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Chunk types
# ---------------------------------------------------------------------------

@dataclass
class ChunkMetadata:
    """Metadata attached to each text chunk for filtering and retrieval."""

    municipality: str
    county: str
    chapter: str
    section: str
    section_title: str
    zone_codes: list[str]
    chunk_index: int
    municode_node_id: str


@dataclass
class TextChunk:
    """A text chunk ready for embedding, with its metadata."""

    text: str
    metadata: ChunkMetadata


# ---------------------------------------------------------------------------
# Search types
# ---------------------------------------------------------------------------

@dataclass
class SearchResult:
    """A single result from hybrid search."""

    section: str
    section_title: str
    zone_codes: list[str]
    chunk_text: str
    score: float
    municipality: str


# ---------------------------------------------------------------------------
# Fallback configs — verified against live Municode API.
# Used when Library API discovery is unavailable.
# ---------------------------------------------------------------------------

_FALLBACK_CONFIGS: dict[str, MunicodeConfig] = {
    "miami_dade": MunicodeConfig(
        municipality="Unincorporated Miami-Dade",
        county="miami_dade",
        client_id=11719,
        product_id=10620,
        job_id=483425,
        zoning_node_id="PTIIICOOR_CH33ZO",
    ),
    "fort_lauderdale": MunicodeConfig(
        municipality="Fort Lauderdale",
        county="broward",
        client_id=2247,
        product_id=13463,
        job_id=482747,
        zoning_node_id="UNLADERE_CH47UNLADERE_ARTIIZODIRE",
    ),
}

MUNICODE_CONFIGS = _FALLBACK_CONFIGS
