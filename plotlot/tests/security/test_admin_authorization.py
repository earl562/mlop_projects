from unittest.mock import AsyncMock, patch

import pytest

from plotlot.api.auth_types import Actor, IdentityRole, capabilities_for_role
from plotlot.api.main import app
from plotlot.api.route_policy import capability_for_route, protected_route_matrix


def _actor(role: IdentityRole) -> Actor:
    return Actor(
        user_id=f"{role.value}-user",
        tenant_id="tenant-a",
        role=role,
        capabilities=capabilities_for_role(role),
    )


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/admin/chunks/stats"),
        ("post", "/api/v1/admin/ingest"),
        ("delete", "/api/v1/admin/cache"),
        ("delete", "/api/v1/admin/chunks"),
        ("post", "/api/v1/workspaces"),
        ("post", "/api/v1/connectors/email/configure"),
    ],
)
async def test_analyst_cannot_reach_admin_or_destructive_handler(
    client,
    method: str,
    path: str,
) -> None:
    with (
        patch(
            "plotlot.api.security_middleware.get_current_user",
            new=AsyncMock(return_value=_actor(IdentityRole.ANALYST).as_request_user()),
        ),
        patch("plotlot.api.routes.get_session", new=AsyncMock()) as session_factory,
    ):
        response = await client.request(method, path, json={})

    assert response.status_code == 403
    session_factory.assert_not_awaited()


def test_every_non_public_route_has_an_explicit_role_policy() -> None:
    matrix = protected_route_matrix(app)
    api_routes = {
        (method, route.path)
        for route in app.routes
        if route.path.startswith("/api/")
        for method in route.methods
        if method not in {"HEAD", "OPTIONS"}
    }

    assert matrix.covered_routes == api_routes
    assert matrix.missing_routes == frozenset()


def test_non_api_readiness_routes_remain_public() -> None:
    assert capability_for_route("GET", "/health") is None


@pytest.mark.parametrize(
    ("method", "path", "role", "allowed"),
    [
        ("POST", "/api/v1/workspaces", IdentityRole.OWNER, True),
        ("POST", "/api/v1/workspaces", IdentityRole.ADMIN, False),
        ("GET", "/api/v1/admin/chunks/stats", IdentityRole.ADMIN, True),
        ("POST", "/api/v1/connectors/email/send", IdentityRole.ADMIN, True),
        ("POST", "/api/v1/approvals/id/approve", IdentityRole.REVIEWER, True),
        ("POST", "/api/v1/releases/id/release", IdentityRole.REVIEWER, True),
        ("POST", "/api/v1/analyses", IdentityRole.ANALYST, True),
        ("GET", "/api/v1/analyses", IdentityRole.VIEWER, True),
    ],
)
def test_route_role_matrix_is_least_privilege(
    method: str,
    path: str,
    role: IdentityRole,
    allowed: bool,
) -> None:
    capability = capability_for_route(method, path)

    assert capability is not None
    assert (capability in capabilities_for_role(role)) is allowed
