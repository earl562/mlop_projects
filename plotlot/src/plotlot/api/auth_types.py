"""Typed identity roles, capabilities, and verified actor claims."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class IdentityRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    ANALYST = "analyst"
    REVIEWER = "reviewer"
    VIEWER = "viewer"


class Capability(StrEnum):
    MANAGE_WORKSPACE = "workspace:manage"
    MANAGE_MEMBERS = "members:manage"
    MANAGE_SERVICE_PRINCIPALS = "service-principals:manage"
    ADMINISTER_SYSTEM = "system:admin"
    USE_DEBUG_TOOLS = "debug:use"
    PERFORM_DESTRUCTIVE_ACTION = "destructive:perform"
    MANAGE_CONNECTORS = "connectors:manage"
    RUN_ANALYSIS = "analysis:run"
    REVIEW_ANALYSIS = "analysis:review"
    RELEASE_EXTERNAL = "analysis:release"
    VIEW_ANALYSIS = "analysis:view"


_ROLE_CAPABILITIES: dict[IdentityRole, frozenset[Capability]] = {
    IdentityRole.OWNER: frozenset(Capability),
    IdentityRole.ADMIN: frozenset(
        {
            Capability.MANAGE_MEMBERS,
            Capability.MANAGE_SERVICE_PRINCIPALS,
            Capability.ADMINISTER_SYSTEM,
            Capability.USE_DEBUG_TOOLS,
            Capability.PERFORM_DESTRUCTIVE_ACTION,
            Capability.MANAGE_CONNECTORS,
            Capability.RUN_ANALYSIS,
            Capability.REVIEW_ANALYSIS,
            Capability.VIEW_ANALYSIS,
        }
    ),
    IdentityRole.ANALYST: frozenset({Capability.RUN_ANALYSIS, Capability.VIEW_ANALYSIS}),
    IdentityRole.REVIEWER: frozenset(
        {
            Capability.REVIEW_ANALYSIS,
            Capability.RELEASE_EXTERNAL,
            Capability.VIEW_ANALYSIS,
        }
    ),
    IdentityRole.VIEWER: frozenset({Capability.VIEW_ANALYSIS}),
}


def capabilities_for_role(role: IdentityRole) -> frozenset[Capability]:
    return _ROLE_CAPABILITIES[role]


@dataclass(frozen=True, slots=True)
class Actor:
    user_id: str
    tenant_id: str | None
    role: IdentityRole
    capabilities: frozenset[Capability]
    email: str | None = None

    def as_request_user(self) -> dict[str, str | None | frozenset[Capability]]:
        """Return the legacy request-state shape consumed by existing routes."""
        return {
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "role": self.role.value,
            "email": self.email,
            "capabilities": self.capabilities,
        }


@dataclass(frozen=True, slots=True)
class ServicePrincipalScope:
    tenant_id: str
    required_action: str
    revoked_principal_ids: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class ServicePrincipalClaims:
    principal_id: str
    tenant_id: str
    actions: frozenset[str]
