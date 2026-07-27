from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from plotlot.protocol.router import router


protocol_app = FastAPI(
    title="PlotLot ByRight Engine Protocol",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
protocol_app.include_router(router)


def protocol_openapi_document() -> dict[str, Any]:
    return protocol_app.openapi()
