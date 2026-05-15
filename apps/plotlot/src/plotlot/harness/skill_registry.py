"""Skill registry for repo-owned PlotLot workflows."""

from __future__ import annotations

from plotlot.harness.contracts import Skill


class SkillRegistry:
    """In-memory registry of available harness skills."""

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        self._skills[skill.name] = skill

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def list_names(self) -> list[str]:
        return sorted(self._skills)

    def match(self, intent: str) -> Skill | None:
        """Return a skill for a coarse intent string."""

        if not intent:
            return self._skills.get("zoning_research")

        if intent in self._skills:
            return self._skills[intent]

        aliases = {
            "zoning_lookup": "zoning_research",
            "parcel_analysis": "zoning_research",
            "zoning_research": "zoning_research",
            "site_search": "site_selection",
            "site_selection": "site_selection",
            "data_center_site_search": "site_selection",
        }
        canonical = aliases.get(intent)
        if canonical and canonical in self._skills:
            return self._skills[canonical]

        return self._skills.get("zoning_research")

    def route(self, prompt: str) -> Skill | None:
        """Route a prompt to a skill by simple trigger matching."""

        lowered = prompt.lower()
        for skill in self._skills.values():
            if any(trigger in lowered for trigger in skill.triggers):
                return skill
        return None
