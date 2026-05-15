"""Deterministic intent routing for harness skills.

The first harness router is intentionally lightweight and non-LLM. It maps an
incoming message to a coarse skill name based on keyword triggers.
"""

from __future__ import annotations


class IntentRouter:
    """Route a free-form message into a skill name."""

    def route(self, message: str) -> str:
        text = (message or "").lower()

        if any(
            keyword in text
            for keyword in [
                "zoning",
                "setback",
                "density",
                "allowed use",
                "max units",
                "far",
                "lot coverage",
                "height limit",
                "dimensional standard",
            ]
        ):
            return "zoning_research"

        if any(
            keyword in text
            for keyword in [
                "site search",
                "find sites",
                "data center",
                "datacenter",
                "warehouse",
                "industrial",
            ]
        ):
            return "site_selection"

        if any(
            keyword in text
            for keyword in [
                "email",
                "follow up",
                "follow-up",
                "seller",
                "broker",
                "crm",
                "lead",
                "outreach",
            ]
        ):
            return "outreach_ops"

        if any(
            keyword in text
            for keyword in [
                "report",
                "memo",
                "document",
                "export",
                "pdf",
                "doc",
            ]
        ):
            return "document_generation"

        return "zoning_research"
