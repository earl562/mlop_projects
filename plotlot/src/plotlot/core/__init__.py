"""Compat shim — re-exports from workspace shared package.

Existing code imports from plotlot.core — this redirects to shared.types and shared.errors.
The originals remain in place for direct import if needed.
"""

from shared.errors import (  # noqa: F401
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
from shared.types import (  # noqa: F401
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
    "ChunkMetadata", "ConfigurationError", "DegradedError", "ExternalAPIError",
    "FatalError", "GeocodingError", "LowConfidenceError", "MunicodeConfig",
    "NoDataError", "OutOfCoverageError", "PartialExtractionError",
    "PlotLotError", "PropertyLookupError", "PropertyRecord", "RateLimitError",
    "RawSection", "RetriableError", "SearchResult", "Setbacks",
    "TextChunk", "TimeoutError", "TocNode", "ZoningReport",
]
