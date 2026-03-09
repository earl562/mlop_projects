"""Structured error taxonomy for PlotLot pipeline.

Classifies errors into three categories:
- Retriable: transient network/API failures that may succeed on retry
- Fatal: missing data or configuration that cannot be recovered
- Degraded: partial failure where the pipeline can continue with reduced quality
"""


class PlotLotError(Exception):
    """Base error for all PlotLot errors."""


# --- Retriable errors (network, rate limits, timeouts) ---


class RetriableError(PlotLotError):
    """Transient error that may succeed on retry."""


class ExternalAPIError(RetriableError):
    """External API returned an error (Municode, NVIDIA, Geocodio, ArcGIS)."""

    def __init__(self, service: str, status_code: int | None = None, message: str = ""):
        self.service = service
        self.status_code = status_code
        super().__init__(f"{service} API error ({status_code}): {message}")


class RateLimitError(RetriableError):
    """API rate limit exceeded."""

    def __init__(self, service: str, retry_after: float | None = None):
        self.service = service
        self.retry_after = retry_after
        super().__init__(
            f"{service} rate limited"
            + (f" (retry after {retry_after}s)" if retry_after else "")
        )


class TimeoutError(RetriableError):  # noqa: A001
    """Operation timed out."""

    def __init__(self, operation: str, timeout_seconds: float):
        self.operation = operation
        self.timeout_seconds = timeout_seconds
        super().__init__(f"{operation} timed out after {timeout_seconds}s")


# --- Fatal errors (cannot recover) ---


class FatalError(PlotLotError):
    """Unrecoverable error — pipeline must stop."""


class OutOfCoverageError(FatalError):
    """Address is outside the supported coverage area."""

    def __init__(self, address: str, county: str | None = None):
        self.address = address
        self.county = county
        msg = f"Address outside coverage: {address}"
        if county:
            msg += f" (county: {county})"
        super().__init__(msg)


class GeocodingError(FatalError):
    """Address could not be geocoded."""

    def __init__(self, address: str, reason: str = ""):
        self.address = address
        super().__init__(f"Geocoding failed for {address}: {reason}")


class NoDataError(FatalError):
    """No zoning data available for the municipality."""

    def __init__(self, municipality: str):
        self.municipality = municipality
        super().__init__(f"No zoning data ingested for {municipality}")


class ConfigurationError(FatalError):
    """Missing or invalid configuration."""


# --- Degraded errors (partial results possible) ---


class DegradedError(PlotLotError):
    """Partial failure — pipeline can continue with reduced quality."""


class PropertyLookupError(DegradedError):
    """Property record lookup failed — can proceed without property data."""

    def __init__(self, address: str, reason: str = ""):
        self.address = address
        super().__init__(f"Property lookup failed for {address}: {reason}")


class LowConfidenceError(DegradedError):
    """LLM extraction returned low confidence results."""

    def __init__(self, confidence: str, reason: str = ""):
        self.confidence = confidence
        super().__init__(f"Low confidence extraction ({confidence}): {reason}")


class PartialExtractionError(DegradedError):
    """Some zoning parameters could not be extracted."""

    def __init__(self, missing_fields: list[str]):
        self.missing_fields = missing_fields
        super().__init__(f"Missing zoning fields: {', '.join(missing_fields)}")
