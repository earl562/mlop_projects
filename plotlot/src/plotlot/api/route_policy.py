from dataclasses import dataclass
from http import HTTPMethod

from fastapi import FastAPI
from fastapi.routing import APIRoute

from plotlot.api.auth_types import Capability


RouteKey = tuple[str, str]


@dataclass(frozen=True, slots=True)
class RouteMatrix:
    covered_routes: frozenset[RouteKey]
    missing_routes: frozenset[RouteKey]
    policies: dict[RouteKey, Capability | None]


def capability_for_route(method: str, path: str) -> Capability | None:
    if not path.startswith("/api/"):
        return None
    if path == "/api/v1/stripe/webhook":
        return None
    if path.startswith("/api/v1/admin/"):
        if method == HTTPMethod.DELETE:
            return Capability.PERFORM_DESTRUCTIVE_ACTION
        return Capability.ADMINISTER_SYSTEM
    if "/debug" in path:
        return Capability.USE_DEBUG_TOOLS
    if path.startswith("/api/v1/connectors/"):
        return Capability.MANAGE_CONNECTORS
    if path == "/api/v1/workspaces" and method == HTTPMethod.POST:
        return Capability.MANAGE_WORKSPACE
    if path.endswith("/release"):
        return Capability.RELEASE_EXTERNAL
    if path.startswith("/api/v1/approvals/") and method == HTTPMethod.POST:
        return Capability.REVIEW_ANALYSIS
    if method == HTTPMethod.DELETE:
        return Capability.PERFORM_DESTRUCTIVE_ACTION
    if method in {HTTPMethod.POST, HTTPMethod.PUT, HTTPMethod.PATCH}:
        return Capability.RUN_ANALYSIS
    return Capability.VIEW_ANALYSIS


def protected_route_matrix(app: FastAPI) -> RouteMatrix:
    api_routes = {
        (method, route.path)
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith("/api/")
        for method in route.methods
        if method not in {HTTPMethod.HEAD, HTTPMethod.OPTIONS}
    }
    policies = {route: capability_for_route(method=route[0], path=route[1]) for route in api_routes}
    return RouteMatrix(
        covered_routes=frozenset(policies),
        missing_routes=frozenset(api_routes.difference(policies)),
        policies=policies,
    )
