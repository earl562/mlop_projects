from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from plotlot.harness.contracts.base import HarnessContract


class WebLookupStatus(StrEnum):
    SUCCESS = "success"
    NOT_CONFIGURED = "not_configured"
    QUOTA_EXCEEDED = "quota_exceeded"
    AUTH_ERROR = "auth_error"
    ERROR = "error"


class WebSearchProvider(StrEnum):
    AUTO = "auto"
    JINA = "jina"
    EXA = "exa"


class WebSearchResultItem(HarnessContract):
    title: str = ""
    url: str = ""
    description: str = ""
    content: str = ""


class WebSearchResult(HarnessContract):
    status: WebLookupStatus
    provider: WebSearchProvider = WebSearchProvider.EXA
    results: list[WebSearchResultItem] = Field(default_factory=list)
    message: str | None = None
