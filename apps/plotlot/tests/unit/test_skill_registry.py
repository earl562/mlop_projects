"""Unit tests for SkillRegistry behavior."""

from __future__ import annotations

from plotlot.harness.contracts import SkillInput, SkillOutput
from plotlot.harness.skill_registry import SkillRegistry


class _NamedSkill:
    def __init__(self, name: str) -> None:
        self.name = name
        self.triggers = (name.replace("_", " "),)

    async def run(self, runtime, skill_input: SkillInput) -> SkillOutput:
        _ = (runtime, skill_input)
        return SkillOutput(status="success", summary=self.name)


def test_registry_match_aliases_to_registered_skills() -> None:
    registry = SkillRegistry()
    registry.register(_NamedSkill("zoning_research"))
    registry.register(_NamedSkill("site_selection"))

    assert registry.match("zoning_lookup").name == "zoning_research"
    assert registry.match("parcel_analysis").name == "zoning_research"
    assert registry.match("data_center_site_search").name == "site_selection"
