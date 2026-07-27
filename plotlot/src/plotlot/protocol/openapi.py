from __future__ import annotations

import re
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import (
    http_exception_handler,
    request_validation_exception_handler,
)
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from plotlot.protocol.errors import (
    ProtocolErrorCategory,
    ProtocolErrorCode,
    ProtocolErrorV1,
)
from plotlot.protocol.router import router


type JsonValue = str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
_REQUEST_ID = re.compile(r"^request_[A-Za-z0-9_-]+$")
_ENGINE_RUN_ID = re.compile(r"^engrun_[A-Za-z0-9_-]+$")
_ENGINE_REVISION_ID = re.compile(r"^engrev_[A-Za-z0-9_-]+$")
_HTTP_ERRORS: dict[int, tuple[ProtocolErrorCode, ProtocolErrorCategory, bool, str]] = {
    400: ("REQUEST_INVALID", "validation", False, "Protocol request is invalid."),
    401: ("AUTH_CONTEXT_INVALID", "authentication", False, "Authentication context is invalid."),
    404: ("RUN_NOT_FOUND", "not-found", False, "Requested engine resource was not found."),
    409: ("STALE_REVISION", "conflict", False, "Engine state conflicts with this request."),
    422: ("REQUEST_INVALID", "validation", False, "Protocol request validation failed."),
    429: ("ENGINE_UNAVAILABLE", "transient", True, "Engine request rate limit exceeded."),
    500: ("INTERNAL_ERROR", "internal", False, "Internal protocol error."),
    503: ("ENGINE_UNAVAILABLE", "transient", True, "PlotLot analysis engine is unavailable."),
    504: ("DEADLINE_EXCEEDED", "transient", True, "Protocol deadline was exceeded."),
}


def _nested(value: JsonValue, *keys: str) -> JsonValue:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _matching(value: JsonValue, pattern: re.Pattern[str]) -> str | None:
    return value if isinstance(value, str) and pattern.fullmatch(value) else None


def _correlation(request: Request, body: JsonValue = None) -> tuple[str, str | None, str | None]:
    request_id = _matching(request.headers.get("x-request-id"), _REQUEST_ID)
    if request_id is None:
        request_id = _matching(_nested(body, "host", "request_id"), _REQUEST_ID)
    engine_run_id = _matching(request.path_params.get("engine_run_id"), _ENGINE_RUN_ID)
    engine_revision_id = _matching(
        request.path_params.get("engine_revision_id"),
        _ENGINE_REVISION_ID,
    )
    return request_id or "request_unavailable", engine_run_id, engine_revision_id


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: ProtocolErrorCode,
    category: ProtocolErrorCategory,
    retryable: bool,
    message: str,
    body: JsonValue = None,
) -> JSONResponse:
    request_id, engine_run_id, engine_revision_id = _correlation(request, body)
    error = ProtocolErrorV1.model_validate(
        {
            "schema_version": "ProtocolErrorV1",
            "code": code,
            "category": category,
            "retryable": retryable,
            "http_status": status_code,
            "message": message,
            "request_id": request_id,
            "engine_run_id": engine_run_id,
            "engine_revision_id": engine_revision_id,
        },
    )
    return JSONResponse(status_code=status_code, content=error.model_dump(mode="json"))


async def protocol_validation_error(
    request: Request,
    exception: RequestValidationError,
) -> Response:
    if not request.url.path.startswith("/api/v1/engine"):
        return await request_validation_exception_handler(request, exception)
    fields = {str(part) for error in exception.errors() for part in error.get("loc", ())}
    code: ProtocolErrorCode = (
        "CURSOR_INVALID" if fields.intersection({"cursor", "after_cursor"}) else "REQUEST_INVALID"
    )
    message = (
        "Protocol cursor validation failed."
        if code == "CURSOR_INVALID"
        else "Protocol request validation failed."
    )
    return _error_response(
        request,
        status_code=422,
        code=code,
        category="validation",
        retryable=False,
        message=message,
        body=exception.body,
    )


async def protocol_http_error(
    request: Request,
    exception: StarletteHTTPException,
) -> Response:
    if not request.url.path.startswith("/api/v1/engine"):
        return await http_exception_handler(request, exception)
    code, category, retryable, message = _HTTP_ERRORS.get(exception.status_code, _HTTP_ERRORS[500])
    status_code = exception.status_code if exception.status_code in _HTTP_ERRORS else 500
    return _error_response(
        request,
        status_code=status_code,
        code=code,
        category=category,
        retryable=retryable,
        message=message,
    )


async def _installed_validation_handler(request: Request, exception: Exception) -> Response:
    if not isinstance(exception, RequestValidationError):
        raise exception
    return await protocol_validation_error(request, exception)


async def _installed_http_handler(request: Request, exception: Exception) -> Response:
    if not isinstance(exception, StarletteHTTPException):
        raise exception
    return await protocol_http_error(request, exception)


def install_engine_protocol(app: FastAPI) -> None:
    if getattr(app.state, "engine_protocol_installed", False):
        return
    app.include_router(router)
    app.add_exception_handler(RequestValidationError, _installed_validation_handler)
    app.add_exception_handler(StarletteHTTPException, _installed_http_handler)
    app.state.engine_protocol_installed = True


protocol_app = FastAPI(
    title="PlotLot ByRight Engine Protocol",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
install_engine_protocol(protocol_app)


def protocol_openapi_document() -> dict[str, Any]:
    return protocol_app.openapi()
