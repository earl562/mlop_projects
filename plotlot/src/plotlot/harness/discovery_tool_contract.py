from __future__ import annotations

from plotlot.land_use.models import ToolContract, ToolRiskClass


DISCOVERY_TOOL_CONTRACTS: dict[str, ToolContract] = {
    "discover_open_data_layers": ToolContract(
        name="discover_open_data_layers",
        description="Discover ArcGIS Hub/open-data layers for a jurisdiction.",
        risk_class=ToolRiskClass.EXPENSIVE_READ,
        input_schema={
            "type": "object",
            "properties": {
                "county": {"type": "string", "minLength": 2},
                "state": {"type": "string", "minLength": 2, "maxLength": 2},
                "lat": {"type": "number"},
                "lng": {"type": "number"},
            },
            "required": ["county", "state", "lat", "lng"],
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
    "discover_municode_authorities": ToolContract(
        name="discover_municode_authorities",
        description="Discover Municode zoning authorities for a county/state.",
        risk_class=ToolRiskClass.EXPENSIVE_READ,
        input_schema={
            "type": "object",
            "properties": {
                "county": {"type": "string", "minLength": 2},
                "state": {"type": "string", "minLength": 2, "maxLength": 2},
            },
            "required": ["county", "state"],
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
    "discover_code_authorities": ToolContract(
        name="discover_code_authorities",
        description=(
            "Discover county ordinance/code providers across Municode, eCode360, "
            "American Legal, Code Publishing, Open Legal Codes, and official county pages."
        ),
        risk_class=ToolRiskClass.EXPENSIVE_READ,
        input_schema={
            "type": "object",
            "properties": {
                "county": {"type": "string", "minLength": 2},
                "state": {"type": "string", "minLength": 2, "maxLength": 2},
                "include_web_fallback": {"type": "boolean"},
            },
            "required": ["county", "state"],
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
    "search_code_authority_live": ToolContract(
        name="search_code_authority_live",
        description="Search a discovered Open Legal Codes jurisdiction for ordinance text.",
        risk_class=ToolRiskClass.EXPENSIVE_READ,
        input_schema={
            "type": "object",
            "properties": {
                "jurisdiction_id": {"type": "string", "minLength": 2},
                "query": {"type": "string", "minLength": 1},
                "limit": {"type": "integer", "minimum": 1, "maximum": 25},
            },
            "required": ["jurisdiction_id", "query"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "results": {"type": "array"},
                "evidence": {"type": "array"},
                "message": {"type": "string"},
            },
        },
        budget_cents=25,
    ),
    "web_search": ToolContract(
        name="web_search",
        description="Last-resort web search for sources not present in local data.",
        risk_class=ToolRiskClass.EXPENSIVE_READ,
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        budget_cents=25,
    ),
}
