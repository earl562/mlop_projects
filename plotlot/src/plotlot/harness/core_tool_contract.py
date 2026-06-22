from __future__ import annotations

from plotlot.land_use.models import ToolContract, ToolRiskClass


CORE_TOOL_CONTRACTS: dict[str, ToolContract] = {
    "geocode_address": ToolContract(
        name="geocode_address",
        description="Resolve an address to municipality/county/state and coordinates.",
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {"address": {"type": "string", "minLength": 3}},
            "required": ["address"],
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
    "lookup_property_info": ToolContract(
        name="lookup_property_info",
        description="Lookup parcel/property facts from county records/GIS.",
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "address": {"type": "string", "minLength": 3},
                "county": {"type": "string", "minLength": 3},
                "state": {"type": "string", "minLength": 2, "maxLength": 2},
                "lat": {"type": "number"},
                "lng": {"type": "number"},
            },
            "required": ["address", "county", "lat", "lng"],
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
}
