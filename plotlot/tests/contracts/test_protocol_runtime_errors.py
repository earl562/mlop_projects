from __future__ import annotations

from typing import Literal, assert_never

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from httpx import Response

from plotlot.api.main import app as production_app
from plotlot.protocol.errors import ProtocolErrorV1
from plotlot.protocol.openapi import install_engine_protocol, protocol_app


client = TestClient(protocol_app, raise_server_exceptions=False)
production_client = TestClient(production_app, raise_server_exceptions=False)
type ProductionScenario = Literal[
    "unavailable",
    "invalid-engine-id",
    "missing-cursor",
    "malformed-body",
]


def _protocol_error(
    response: Response,
    *,
    status_code: int,
    code: str,
    retryable: bool,
) -> ProtocolErrorV1:
    assert response.status_code == status_code
    error = ProtocolErrorV1.model_validate(response.json())
    assert error.http_status == status_code
    assert error.code == code
    assert error.retryable is retryable
    return error


def test_runtime_unavailable_response_is_a_correlated_protocol_error() -> None:
    # Given: a valid run request while engine composition is unavailable.
    response = client.get(
        "/api/v1/engine/runs/engrun_alpha",
        headers={"x-request-id": "request_runtime_503"},
    )

    # When/Then: the 503 body preserves protocol shape and run correlation.
    error = _protocol_error(
        response,
        status_code=503,
        code="ENGINE_UNAVAILABLE",
        retryable=True,
    )
    assert error.request_id == "request_runtime_503"
    assert error.engine_run_id == "engrun_alpha"


def test_invalid_engine_id_is_a_non_retryable_protocol_validation_error() -> None:
    # Given: an engine identifier from the wrong ID family.
    response = client.get(
        "/api/v1/engine/runs/hostrun_wrong",
        headers={"x-request-id": "request_invalid_run"},
    )

    # When/Then: FastAPI's 422 status is preserved without native detail drift.
    error = _protocol_error(
        response,
        status_code=422,
        code="REQUEST_INVALID",
        retryable=False,
    )
    assert error.request_id == "request_invalid_run"
    assert error.engine_run_id is None


def test_missing_cursor_is_a_correlated_cursor_error() -> None:
    # Given: an event-page request without its required cursor.
    response = client.get(
        "/api/v1/engine/runs/engrun_alpha/events",
        headers={"x-request-id": "request_missing_cursor"},
    )

    # When/Then: the 422 response uses the stable cursor error code.
    error = _protocol_error(
        response,
        status_code=422,
        code="CURSOR_INVALID",
        retryable=False,
    )
    assert error.request_id == "request_missing_cursor"
    assert error.engine_run_id == "engrun_alpha"


def test_malformed_body_uses_body_request_correlation() -> None:
    # Given: an opportunity body with a request ID but missing required fields.
    response = client.post(
        "/api/v1/engine/opportunities",
        json={
            "schema_version": "OpportunityCommandV1",
            "host": {"request_id": "request_malformed_body"},
        },
    )

    # When/Then: the malformed body produces the versioned 422 error projection.
    error = _protocol_error(
        response,
        status_code=422,
        code="REQUEST_INVALID",
        retryable=False,
    )
    assert error.request_id == "request_malformed_body"


def _production_error_response(scenario: ProductionScenario) -> Response:
    match scenario:
        case "unavailable":
            return production_client.get(
                "/api/v1/engine/runs/engrun_alpha",
                headers={"x-request-id": "request_production_503"},
            )
        case "invalid-engine-id":
            return production_client.get(
                "/api/v1/engine/runs/hostrun_wrong",
                headers={"x-request-id": "request_production_invalid"},
            )
        case "missing-cursor":
            return production_client.get(
                "/api/v1/engine/runs/engrun_alpha/events",
                headers={"x-request-id": "request_production_cursor"},
            )
        case "malformed-body":
            return production_client.post(
                "/api/v1/engine/opportunities",
                json={
                    "schema_version": "OpportunityCommandV1",
                    "host": {"request_id": "request_production_body"},
                },
            )
        case _:
            assert_never(scenario)


@pytest.mark.parametrize(
    ("scenario", "status_code", "code", "retryable"),
    [
        ("unavailable", 503, "ENGINE_UNAVAILABLE", True),
        ("invalid-engine-id", 422, "REQUEST_INVALID", False),
        ("missing-cursor", 422, "CURSOR_INVALID", False),
        ("malformed-body", 422, "REQUEST_INVALID", False),
    ],
)
def test_production_app_emits_protocol_errors(
    scenario: ProductionScenario,
    status_code: int,
    code: str,
    retryable: bool,
) -> None:
    # Given: one real production application engine request that fails.
    response = _production_error_response(scenario)

    # When/Then: production emits the same strict error transport as protocol_app.
    _protocol_error(
        response,
        status_code=status_code,
        code=code,
        retryable=retryable,
    )


def test_production_non_engine_errors_keep_fastapi_default_shape() -> None:
    response = production_client.get("/not-a-production-route")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found"}


@pytest.mark.parametrize(
    ("status_code", "code", "retryable"),
    [
        (400, "REQUEST_INVALID", False),
        (401, "AUTH_CONTEXT_INVALID", False),
        (404, "RUN_NOT_FOUND", False),
        (409, "STALE_REVISION", False),
        (422, "REQUEST_INVALID", False),
        (503, "ENGINE_UNAVAILABLE", True),
        (504, "DEADLINE_EXCEEDED", True),
    ],
)
def test_every_declared_http_error_status_uses_protocol_shape(
    status_code: int,
    code: str,
    retryable: bool,
) -> None:
    # Given: an isolated route raising one declared protocol error status.
    error_app = FastAPI()
    install_engine_protocol(error_app)
    install_engine_protocol(error_app)

    @error_app.get("/api/v1/engine/test-error")
    async def raise_declared_error() -> None:
        raise HTTPException(status_code=status_code)

    # When: the declared error crosses the ASGI boundary.
    response = TestClient(error_app).get(
        "/api/v1/engine/test-error",
        headers={"x-request-id": "request_declared_status"},
    )

    # Then: status and retryability are preserved in a versioned error body.
    assert (
        sum(
            getattr(route, "path", None) == "/api/v1/engine/opportunities"
            for route in error_app.routes
        )
        == 1
    )
    error = _protocol_error(
        response,
        status_code=status_code,
        code=code,
        retryable=retryable,
    )
    assert error.request_id == "request_declared_status"
