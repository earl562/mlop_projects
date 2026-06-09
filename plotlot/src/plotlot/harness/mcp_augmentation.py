"""MCP tool description augmentation pipeline.

Per MCP Tool Descriptions Are Smelly (Paper 19, arXiv 2602.14878):
Tool descriptions are the interface contract between agents and tools.
The 6-component standard improves agent tool selection accuracy:
  1. Purpose — what the tool does (one sentence)
  2. Parameters — each parameter: name, type, description, required
  3. Usage — when to use and when NOT to use
  4. Examples — 1-2 concise input/output examples
  5. Limitations — known edge cases, rate limits, data freshness
  6. Error — common error patterns and recovery guidance
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AugmentedDescription:
    name: str
    purpose: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)
    usage: str = ""
    examples: list[dict[str, Any]] = field(default_factory=list)
    limitations: str = ""
    error_guidance: str = ""

    def to_tool_description(self) -> str:
        parts = [f"Tool: {self.name}"]
        if self.purpose:
            parts.append(f"Purpose: {self.purpose}")
        if self.usage:
            parts.append(f"When to use: {self.usage}")
        if self.examples:
            parts.append("Examples:")
            for ex in self.examples[:2]:
                parts.append(f"  Input: {ex.get('input', '')}")
                parts.append(f"  Output: {ex.get('output', '')}")
        if self.limitations:
            parts.append(f"Limitations: {self.limitations}")
        if self.error_guidance:
            parts.append(f"Errors: {self.error_guidance}")
        return "\n".join(parts)

    def to_context_fragment(self) -> str:
        """Minimal description for progressive disclosure context."""
        base = f"{self.name}: {self.purpose}"
        if self.usage:
            base += f" ({self.usage})"
        return base


class MCPAugmentationPipeline:
    """Enhance MCP tool descriptions with the 6-component standard.

    Takes raw tool contracts and produces augmented descriptions
    that improve agent tool selection accuracy.

    Usage:
        pipeline = MCPAugmentationPipeline()
        pipeline.register("zoning_lookup", AugmentedDescription(
            name="zoning_lookup",
            purpose="Query zoning database by parcel ID to retrieve zone district and dimensional standards.",
            parameters={"parcel_id": {"type": "string", "required": True}},
            usage="Use for zoning compliance checks. NOT for permit fee calculation (use fee_calculator).",
            limitations="Data cached for 24 hours. Newly annexed parcels may not appear.",
            error_guidance="If parcel not found, try alternative identifier (address, APN) via property_lookup.",
        ))
        desc = pipeline.get_description("zoning_lookup")
    """

    def __init__(self):
        self._augmentations: dict[str, AugmentedDescription] = {}
        self._defaults = {
            "purpose": "No description available.",
            "limitations": "Unknown.",
            "error_guidance": "If errors occur, retry with adjusted parameters.",
        }

    def register(self, name: str, desc: AugmentedDescription) -> None:
        for key, default in self._defaults.items():
            if not getattr(desc, key):
                setattr(desc, key, default)
        self._augmentations[name] = desc

    def register_from_template(
        self,
        name: str,
        purpose: str,
        usage: str = "",
        limitations: str = "",
        error_guidance: str = "",
        **params,
    ) -> AugmentedDescription:
        """Quick registration from keyword arguments."""
        desc = AugmentedDescription(
            name=name,
            purpose=purpose,
            parameters=params,
            usage=usage,
            limitations=limitations,
            error_guidance=error_guidance,
        )
        self._augmentations[name] = desc
        return desc

    def get_description(self, name: str) -> str:
        """Full augmented description as a string."""
        desc = self._augmentations.get(name)
        if desc:
            return desc.to_tool_description()
        return f"Tool: {name}\nPurpose: {self._defaults['purpose']}"

    def get_context_fragment(self, name: str) -> str:
        """Minimal description for progressive disclosure."""
        desc = self._augmentations.get(name)
        if desc:
            return desc.to_context_fragment()
        return f"{name}: No description."

    def augment_existing(self, name: str, description: str) -> str:
        """Augment an existing raw description with the 6-component template."""
        if name in self._augmentations:
            return self.get_description(name)
        return description

    def list_augmented(self) -> list[str]:
        return list(self._augmentations.keys())

    def export_context(self) -> str:
        """Export all augmented descriptions as a single context block."""
        fragments = []
        for name in sorted(self._augmentations.keys()):
            fragments.append(self.get_context_fragment(name))
        return "\n".join(fragments)
