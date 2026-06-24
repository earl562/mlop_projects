"""Skill registry — maps skill_name to async handler callable.

Handlers are registered via the @register_skill decorator and looked up
by the AnalysisRun executor to dispatch execution by skill_name.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class HandlerResult:
    """Result returned by a skill handler after execution."""

    output_json: dict[str, Any]
    evidence_ids: list[str] = field(default_factory=list)


HandlerFunc = Callable[[dict[str, Any]], Awaitable[HandlerResult]]

_skill_registry: dict[str, HandlerFunc] = {}


def register_skill(name: str) -> Callable[[HandlerFunc], HandlerFunc]:
    """Decorator that registers an async handler function under the given skill name.

    Usage:
        @register_skill("single_parcel_feasibility")
        async def handle(inputs: dict[str, Any]) -> HandlerResult:
            ...
    """

    def decorator(func: HandlerFunc) -> HandlerFunc:
        _skill_registry[name] = func
        return func

    return decorator


def get_handler(name: str) -> HandlerFunc:
    """Look up a registered skill handler by name.

    Args:
        name: The skill name (e.g., "single_parcel_feasibility").

    Returns:
        The registered async handler callable.

    Raises:
        KeyError: If no handler is registered for the given name.
    """
    try:
        return _skill_registry[name]
    except KeyError:
        raise KeyError(f"Unknown skill: {name}") from None


def list_skills() -> list[str]:
    """Return a list of all registered skill names."""
    return list(_skill_registry.keys())
