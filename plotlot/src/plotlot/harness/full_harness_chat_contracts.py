from __future__ import annotations

from typing import Final

from plotlot.land_use.models import ToolContract, ToolRiskClass

_FULL_HARNESS_CHAT_TOOL_CONTRACTS: Final = {
    "search_municode": ToolContract(
        name="search_municode",
        description="Search the shared harness Municode source lane.",
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "jurisdiction": {"type": "string", "minLength": 1},
                "query": {"type": "string", "minLength": 1},
            },
            "required": ["jurisdiction", "query"],
        },
        output_schema={"type": "object"},
    ),
    "get_municode_section": ToolContract(
        name="get_municode_section",
        description="Fetch a shared harness Municode section artifact.",
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {"section_id": {"type": "string", "minLength": 1}},
            "required": ["section_id"],
        },
        output_schema={"type": "object"},
    ),
    "extract_ordinance_rules": ToolContract(
        name="extract_ordinance_rules",
        description="Extract deterministic rules from a shared harness Municode section.",
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {"section_id": {"type": "string", "minLength": 1}},
            "required": ["section_id"],
        },
        output_schema={"type": "object"},
    ),
    "search_south_florida_gis": ToolContract(
        name="search_south_florida_gis",
        description="Search the shared South Florida GIS source catalog.",
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "minLength": 1},
                "county": {"type": "string", "minLength": 1},
            },
            "required": ["query"],
        },
        output_schema={"type": "object"},
    ),
    "discover_rehabvaluator_video_sections": ToolContract(
        name="discover_rehabvaluator_video_sections",
        description="Discover public training sources through the shared harness lane.",
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "category": {"type": "string"},
            },
        },
        output_schema={"type": "object"},
    ),
}


def full_harness_chat_tool_contracts() -> dict[str, ToolContract]:
    return dict(_FULL_HARNESS_CHAT_TOOL_CONTRACTS)
