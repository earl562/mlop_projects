"""Skill registry — SKILL.md standard with progressive disclosure.

Per SoK: Agentic Skills (Paper 18, arXiv 2602.20867):
Skills = (C, π, T, R) where:
- C: Applicability condition
- π: Executable policy
- T: Termination condition
- R: Reusable callable interface

Per Interpreter Skills (LangChain blog, May 2026):
Skills can ship TypeScript modules executed in interpreter runtime.
SKILL.md tells the agent WHEN; the module defines HOW.

Seven lifecycle stages: Discovery → Practice → Distillation → Storage → Retrieval → Execution → Update.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class SkillManifest:
    name: str
    description: str
    frontmatter: dict[str, Any] = field(default_factory=dict)
    instructions: str = ""
    module_path: str | None = None  # TypeScript module for interpreter skills
    trust_tier: str = "T3"  # T1 (fully trusted) → T4 (sandbox only)
    verification_gate: str = "G2"  # G1 (none) → G4 (adversarial tested)

    def to_context_fragment(self) -> dict[str, str]:
        """Progressive disclosure: minimal frontmatter shown at startup."""
        return {
            "name": self.name,
            "description": self.description,
            "trust_tier": self.trust_tier,
        }


class SkillRegistry:
    """Registry of skills with progressive disclosure.

    At agent start: only frontmatter (name + description) is disclosed.
    When a skill is relevant: full SKILL.md instructions are loaded.
    """

    def __init__(self, skills_dir: str | None = None):
        self._skills: dict[str, SkillManifest] = {}
        self._skills_dir = skills_dir
        if skills_dir and os.path.isdir(skills_dir):
            self._discover(skills_dir)

    # ---------------------------------------------------------------- discovery
    def _discover(self, directory: str) -> None:
        for root, dirs, files in os.walk(directory):
            if "SKILL.md" in files:
                self._load_skill(Path(root) / "SKILL.md")

    def _load_skill(self, skill_md: Path) -> None:
        try:
            content = skill_md.read_text()
            frontmatter, instructions = self._parse_frontmatter(content)
            name = frontmatter.get("name", skill_md.parent.name)
            desc = frontmatter.get("description", name)
            module_raw = frontmatter.get("metadata")
            module = None
            if isinstance(module_raw, dict):
                module = module_raw.get("module")
            elif isinstance(module_raw, str) and module_raw:
                module = module_raw
            module_path = str(skill_md.parent / module) if module else None
            trust = frontmatter.get("trust_tier", "T3")
            gate = frontmatter.get("verification_gate", "G2")
            self._skills[name] = SkillManifest(
                name=name,
                description=desc,
                frontmatter=frontmatter,
                instructions=instructions,
                module_path=module_path,
                trust_tier=trust,
                verification_gate=gate,
            )
        except Exception:
            pass

    def _parse_frontmatter(self, content: str) -> tuple[dict[str, Any], str]:
        """Parse YAML-like frontmatter from --- delimiters."""
        parts = content.split("---", 2)
        if len(parts) < 3:
            return {}, content
        metadata: dict[str, Any] = {}
        for line in parts[1].strip().split("\n"):
            line = line.strip()
            if ":" in line:
                key, _, val = line.partition(":")
                metadata[key.strip()] = val.strip().strip("\"'")
        return metadata, parts[2].strip()

    # ----------------------------------------------------------------- register
    def register(self, manifest: SkillManifest) -> None:
        self._skills[manifest.name] = manifest

    # ----------------------------------------------------- progressive disclosure
    def frontmatters(self) -> list[dict[str, str]]:
        """Compact disclosure — shown at agent startup. Name + description only."""
        return [s.to_context_fragment() for s in self._skills.values()]

    def get_full(self, name: str) -> SkillManifest | None:
        """Full disclosure — loaded when skill is relevant."""
        return self._skills.get(name)

    def get_instructions(self, name: str) -> str:
        skill = self._skills.get(name)
        return skill.instructions if skill else ""

    def list_names(self) -> list[str]:
        return list(self._skills.keys())

    # ------------------------------------------------------------- trust tiers
    def skills_at_tier(self, max_tier: str) -> list[SkillManifest]:
        tiers = {"T1": 1, "T2": 2, "T3": 3, "T4": 4}
        max_val = tiers.get(max_tier, 4)
        return [s for s in self._skills.values() if tiers.get(s.trust_tier, 4) <= max_val]

    def register_interpreter_skill(
        self,
        name: str,
        description: str,
        module_path: str,
        applicability_condition: str = "",
        trust_tier: str = "T2",
    ) -> SkillManifest:
        """Register an interpreter skill (TypeScript module, not prompt)."""
        manifest = SkillManifest(
            name=name,
            description=description,
            frontmatter={
                "name": name,
                "description": description,
                "metadata": {"module": module_path},
                "trust_tier": trust_tier,
                "verification_gate": "G3",
                "applicability": applicability_condition,
            },
            instructions=f"Import using: const {{ {name.replace('-','_')} }} = await import('@/skills/{name}');",
            module_path=module_path,
            trust_tier=trust_tier,
            verification_gate="G3",
        )
        self._skills[name] = manifest
        return manifest
