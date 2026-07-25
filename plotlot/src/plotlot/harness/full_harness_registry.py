from __future__ import annotations

from dataclasses import dataclass

from plotlot.harness.contracts import AgentRoleSpec, SkillSpec, ToolSpec
from plotlot.harness.full_harness_registry_data import AGENT_ROLES, SKILLS, TOOLS


@dataclass(frozen=True, slots=True)
class RegistryLookupError(Exception):
    registry: str
    name: str

    def __str__(self) -> str:
        return f"{self.registry} entry {self.name!r} is not registered"


def list_skill_specs() -> list[SkillSpec]:
    return list(SKILLS)


def get_skill_spec(name: str) -> SkillSpec:
    return _lookup(SKILLS, registry="skill", name=name)


def list_agent_role_specs() -> list[AgentRoleSpec]:
    return list(AGENT_ROLES)


def get_agent_role_spec(name: str) -> AgentRoleSpec:
    return _lookup(AGENT_ROLES, registry="agent_role", name=name)


def list_tool_specs() -> list[ToolSpec]:
    return list(TOOLS)


def get_tool_spec(name: str) -> ToolSpec:
    return _lookup(TOOLS, registry="tool", name=name)


def _lookup[SpecT: AgentRoleSpec | SkillSpec | ToolSpec](
    specs: list[SpecT],
    *,
    registry: str,
    name: str,
) -> SpecT:
    for spec in specs:
        if spec.name == name:
            return spec
    raise RegistryLookupError(registry=registry, name=name)
