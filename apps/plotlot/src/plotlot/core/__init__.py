"""Core domain types and error taxonomy shared across all plotlot modules."""

from plotlot.core.errors import (
    ConfigurationError,
    DegradedError,
    ExternalAPIError,
    FatalError,
    GeocodingError,
    LowConfidenceError,
    NoDataError,
    OutOfCoverageError,
    PartialExtractionError,
    PlotLotError,
    PropertyLookupError,
    RateLimitError,
    RetriableError,
    TimeoutError,
)
from plotlot.core.types import (
    ChunkMetadata,
    MunicodeConfig,
    PropertyRecord,
    RawSection,
    SearchResult,
    Setbacks,
    TextChunk,
    TocNode,
    ZoningReport,
)

__all__ = [
    # Error taxonomy
    "ConfigurationError",
    "DegradedError",
    "ExternalAPIError",
    "FatalError",
    "GeocodingError",
    "LowConfidenceError",
    "NoDataError",
    "OutOfCoverageError",
    "PartialExtractionError",
    "PlotLotError",
    "PropertyLookupError",
    "RateLimitError",
    "RetriableError",
    "TimeoutError",
    # Domain types
    "ChunkMetadata",
    "MunicodeConfig",
    "PropertyRecord",
    "RawSection",
    "SearchResult",
    "Setbacks",
    "TextChunk",
    "TocNode",
    "ZoningReport",
]
