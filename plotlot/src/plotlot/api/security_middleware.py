from collections.abc import Awaitable, Callable
from http import HTTPMethod
from typing import cast

from fastapi import Request, status
from pydantic import JsonValue, TypeAdapter, ValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from plotlot.api.auth import get_current_user
from plotlot.api.auth_types import Actor, Capability, IdentityRole
from plotlot.api.route_policy import capability_for_route
from plotlot.config import settings
from plotlot.security.context import reset_tenant, set_tenant
from plotlot.security.membership import resolve_actor_membership


RequestUser = dict[str, str | None | frozenset[Capability]]
CallNext = Callable[[Request], Awaitable[Response]]
_JSON: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)
_MUTATING_METHODS = frozenset(
    {HTTPMethod.POST, HTTPMethod.PUT, HTTPMethod.PATCH, HTTPMethod.DELETE}
)
_SERVER_DERIVED_FIELDS = frozenset(
    {
        "actor_user_id",
        "decided_by",
        "requested_by",
        "reviewed_by",
        "role",
        "source_mode",
        "risk_budget_cents",
        "live_network_allowed",
    }
)
_ROLE_CONTEXT_FIELDS = frozenset(
    {
        "actor_user_id",
        "live_network_allowed",
        "risk_budget_cents",
        "source_mode",
        "tenant_id",
        "workspace_id",
    }
)


class TenantAuthorizationMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: CallNext) -> Response:
        return await authorize_request(request, call_next)


def _actor_from_user(user: RequestUser) -> Actor:
    user_id = user["user_id"]
    tenant_id = user["tenant_id"]
    role_value = user["role"]
    email = user["email"]
    if not isinstance(user_id, str) or not isinstance(role_value, str):
        raise TypeError("Verified identity is malformed")
    if tenant_id is not None and not isinstance(tenant_id, str):
        raise TypeError("Verified tenant is malformed")
    if email is not None and not isinstance(email, str):
        raise TypeError("Verified email is malformed")
    role = IdentityRole(role_value)
    capabilities = cast(frozenset[Capability], user["capabilities"])
    return Actor(
        user_id=user_id,
        tenant_id=tenant_id,
        role=role,
        capabilities=capabilities,
        email=email,
    )


def _tenant_values(value: JsonValue) -> set[str]:
    match value:
        case dict() as mapping:
            direct = {
                item
                for key in ("workspace_id", "tenant_id")
                if isinstance((item := mapping.get(key)), str)
            }
            return direct.union(*(_tenant_values(item) for item in mapping.values()))
        case list() as items:
            return set().union(*(_tenant_values(item) for item in items))
        case str() | int() | float() | bool() | None:
            return set()


def _server_derived_fields(
    value: JsonValue,
    *,
    is_root: bool = True,
) -> set[str]:
    match value:
        case dict() as mapping:
            direct = set(_SERVER_DERIVED_FIELDS.difference({"role"}).intersection(mapping))
            if "role" in mapping and (is_root or _ROLE_CONTEXT_FIELDS.intersection(mapping)):
                direct.add("role")
            return direct.union(
                *(_server_derived_fields(item, is_root=False) for item in mapping.values())
            )
        case list() as items:
            return set().union(*(_server_derived_fields(item, is_root=False) for item in items))
        case str() | int() | float() | bool() | None:
            return set()


async def authorize_request(request: Request, call_next: CallNext) -> Response:
    user = await get_current_user(request)
    request.state.user = user
    capability = capability_for_route(request.method, request.url.path)
    if capability is None:
        return await call_next(request)
    if user is None:
        if settings.auth_enabled:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"detail": "Authentication required"},
            )
        return await call_next(request)

    actor = _actor_from_user(user)
    if actor.tenant_id is None:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Tenant membership required"},
        )
    token = set_tenant(actor.tenant_id)
    try:
        if settings.auth_enabled:
            persisted_actor = await resolve_actor_membership(actor)
            if persisted_actor is None:
                return JSONResponse(
                    status_code=status.HTTP_403_FORBIDDEN,
                    content={"detail": "Active tenant membership required"},
                )
            actor = persisted_actor
        if capability not in actor.capabilities:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": f"Missing capability: {capability.value}"},
            )

        body: JsonValue = None
        if request.method in _MUTATING_METHODS and request.headers.get(
            "content-type", ""
        ).startswith("application/json"):
            raw_body = await request.body()
            if raw_body:
                try:
                    body = _JSON.validate_json(raw_body)
                except ValidationError:
                    return JSONResponse(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        content={"detail": "Malformed JSON body"},
                    )

        requested_tenants = set(request.query_params.getlist("workspace_id"))
        requested_tenants.update(request.query_params.getlist("tenant_id"))
        path_parts = request.url.path.split("/")
        if "workspaces" in path_parts:
            workspace_index = path_parts.index("workspaces") + 1
            if workspace_index < len(path_parts):
                requested_tenants.add(path_parts[workspace_index])
        requested_tenants.update(_tenant_values(body))
        if requested_tenants.difference({actor.tenant_id}):
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"detail": "Cross-tenant access denied"},
            )
        forbidden_fields = _server_derived_fields(body)
        if forbidden_fields:
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                content={
                    "detail": "Server-derived fields are not accepted",
                    "fields": sorted(forbidden_fields),
                },
            )

        request.state.actor = actor
        return await call_next(request)
    finally:
        reset_tenant(token)
