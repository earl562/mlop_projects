"""Harness-local connector gateway seam."""

from __future__ import annotations

from plotlot.connectors.contracts import Connector, ConnectorContext, ConnectorRecord


class ConnectorGateway:
    """Small registry that normalizes access to connector providers."""

    def __init__(self, connectors: list[Connector] | None = None) -> None:
        self._connectors = {connector.provider: connector for connector in connectors or []}

    def register(self, connector: Connector) -> None:
        self._connectors[connector.provider] = connector

    async def sync(self, context: ConnectorContext) -> list[ConnectorRecord]:
        connector = self._connectors.get(context.provider)
        if connector is None:
            return []
        return await connector.sync(context)


__all__ = ["Connector", "ConnectorContext", "ConnectorGateway", "ConnectorRecord"]
