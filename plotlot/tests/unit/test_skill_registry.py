"""Unit tests for the skill registry."""

from typing import Any

import pytest

from plotlot.pipeline.skills.registry import (
    HandlerResult,
    get_handler,
    list_skills,
    register_skill,
)


@pytest.mark.asyncio
async def test_register_and_lookup() -> None:
    """Registered skill should be retrievable via get_handler."""

    @register_skill("test_skill_lookup")
    async def handler(inputs: dict[str, Any]) -> HandlerResult:
        return HandlerResult(output_json={"result": "ok"}, evidence_ids=["ev-1"])

    retrieved = get_handler("test_skill_lookup")
    assert retrieved is handler

    result = await retrieved({"any": "input"})
    assert result.output_json == {"result": "ok"}
    assert result.evidence_ids == ["ev-1"]


def test_key_error_on_unknown_skill() -> None:
    """get_handler should raise KeyError with descriptive message for unknown skills."""
    with pytest.raises(KeyError, match="Unknown skill: nonexistent_skill_xyz"):
        get_handler("nonexistent_skill_xyz")


def test_list_skills_includes_registered() -> None:
    """list_skills should include all registered skill names."""

    @register_skill("test_list_skill")
    async def handler(inputs: dict[str, Any]) -> HandlerResult:
        return HandlerResult(output_json={})

    assert "test_list_skill" in list_skills()
