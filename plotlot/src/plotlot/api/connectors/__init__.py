"""Connector Gateway — pluggable outbound integrations for PlotLot.

Phase 5 ships the SMTP email connector. Future connectors (CRM, webhook) follow
the same session-scoped credential pattern.
"""

from plotlot.api.connectors.email import router

__all__ = ["router"]
