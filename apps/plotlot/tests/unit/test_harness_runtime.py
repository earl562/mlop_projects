"""Unit tests for HarnessRuntime execution behavior."""

from __future__ import annotations

import pytest

from plotlot.harness.contracts import SkillInput, SkillOutput
from plotlot.harness.runtime import HarnessRuntime
from plotlot.harness.skill_registry import SkillRegistry


class _EchoSkill:
    name = "zoning_research"
    triggers = ("zoning",)

    async def run(self, runtime, skill_input: SkillInput) -> SkillOutput:
        _ = runtime
        return SkillOutput(status="success", summary=skill_input.prompt)


@pytest.mark.asyncio
async def test_runtime_run_skill_executes_named_skill() -> None:
    registry = SkillRegistry()
    registry.register(_EchoSkill())
    runtime = HarnessRuntime(registry=registry)

    output = await runtime.run_skill("zoning_research", SkillInput(prompt="hello"))

    assert output.status == "success"
    assert output.summary == "hello"


@pytest.mark.asyncio
async def test_runtime_run_skill_returns_no_skill_for_unknown_name() -> None:
    runtime = HarnessRuntime(registry=SkillRegistry())
    output = await runtime.run_skill("unknown_skill", SkillInput(prompt="hello"))

    assert output.status == "no_skill"


def test_default_runtime_exposes_scaffolded_seams() -> None:
    from plotlot.harness.bootstrap import build_default_runtime

    runtime = build_default_runtime()

    assert runtime.evidence is not None
    assert runtime.model_gateway is not None
    assert runtime.connector_gateway is not None
    assert runtime.sandbox is not None
