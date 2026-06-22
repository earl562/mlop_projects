from __future__ import annotations

from plotlot.land_use.models import ToolContract, ToolRiskClass


ORDINANCE_TOOL_CONTRACTS: dict[str, ToolContract] = {
    "search_zoning_ordinance": ToolContract(
        name="search_zoning_ordinance",
        description="Search local ordinance/chunk index for relevant sections.",
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "municipality": {"type": "string", "minLength": 2},
                "query": {"type": "string", "minLength": 1},
            },
            "required": ["municipality", "query"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "results": {"type": "array"},
                "evidence": {"type": "array"},
            },
        },
    ),
    "search_ordinances": ToolContract(
        name="search_ordinances",
        description="Search locally indexed ordinance chunks and return citation-rich results.",
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "municipality": {"type": "string", "minLength": 2},
                "query": {"type": "string", "minLength": 1},
                "limit": {"type": "integer", "minimum": 1, "maximum": 25},
            },
            "required": ["municipality", "query"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "results": {"type": "array"},
                "evidence": {"type": "array"},
            },
            "required": ["status", "results"],
        },
    ),
    "fetch_ordinance_section": ToolContract(
        name="fetch_ordinance_section",
        description="Fetch a specific locally indexed ordinance section/chunk by section_id.",
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "municipality": {"type": "string", "minLength": 2},
                "section_id": {"type": "string", "minLength": 1},
            },
            "required": ["municipality", "section_id"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "result": {"type": "object"},
                "evidence": {"type": "array"},
            },
            "required": ["status", "result"],
        },
    ),
    "search_municode_live": ToolContract(
        name="search_municode_live",
        description="Search Municode live (network) for ordinance sections.",
        risk_class=ToolRiskClass.EXPENSIVE_READ,
        input_schema={
            "type": "object",
            "properties": {
                "municipality": {"type": "string", "minLength": 2},
                "state": {"type": "string", "minLength": 2, "maxLength": 2},
                "query": {"type": "string", "minLength": 1},
                "limit": {"type": "integer", "minimum": 1, "maximum": 25},
            },
            "required": ["municipality", "query"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "results": {"type": "array"},
                "evidence": {"type": "array"},
            },
        },
        budget_cents=25,
    ),
}
