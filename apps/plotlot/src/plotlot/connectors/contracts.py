"""Stable connector contracts for external systems."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass(slots=True)
class ConnectorContext:
    workspace_id: str
    provider: str
    connection_id: str | None = None


@dataclass(slots=True)
class ConnectorRecord:
    external_id: str
    record_type: str
    title: str
    fields: dict[str, Any] = field(default_factory=dict)
    source_url: str | None = None
    modified_at: datetime | None = None


class Connector(Protocol):
    provider: str

    async def sync(self, context: ConnectorContext) -> list[ConnectorRecord]:
        """Sync provider records into normalized connector records."""
