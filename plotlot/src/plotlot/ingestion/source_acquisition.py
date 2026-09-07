from __future__ import annotations

from enum import StrEnum, unique

from plotlot.core.errors import PlotLotError


@unique
class SourceFailureReason(StrEnum):
    HTTP_ERROR = "http_error"
    TRANSPORT_ERROR = "transport_error"
    PARSE_ERROR = "parse_error"
    IDENTITY_MISMATCH = "identity_mismatch"
    EMPTY_CONTENT = "empty_content"
    DEPTH_LIMIT = "depth_limit"
    PAGE_LIMIT = "page_limit"
    PROBE_LIMIT = "probe_limit"


class SourceAcquisitionError(PlotLotError):
    def __init__(
        self,
        source_url: str,
        reason: SourceFailureReason,
        status_code: int | None = None,
    ) -> None:
        self.source_url = source_url
        self.reason = reason
        self.status_code = status_code
        super().__init__(
            f"Source acquisition incomplete ({reason}); no new source records accepted."
        )
