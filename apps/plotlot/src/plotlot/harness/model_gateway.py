"""Harness-local model gateway seam.

The product runtime depends on this narrow boundary rather than a specific
provider implementation. A no-op implementation keeps the initial harness
incremental and testable.
"""

from __future__ import annotations

from plotlot.gateways.model_gateway import ModelGateway, ModelRequest, ModelResponse


class NoopModelGateway:
    """Placeholder model gateway used until routed model profiles are wired in."""

    async def complete(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            content="",
            provider="noop",
            model=request.profile,
            usage={},
            tool_calls=[],
        )


__all__ = ["ModelGateway", "ModelRequest", "ModelResponse", "NoopModelGateway"]
