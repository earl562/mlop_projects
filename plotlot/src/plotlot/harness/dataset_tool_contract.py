from __future__ import annotations

from plotlot.land_use.models import ToolContract, ToolRiskClass


DATASET_TOOL_CONTRACTS: dict[str, ToolContract] = {
    "search_properties": ToolContract(
        name="search_properties",
        description="Bulk property search across static and dynamically discovered county datasets.",
        risk_class=ToolRiskClass.EXPENSIVE_READ,
        input_schema={
            "type": "object",
            "properties": {
                "county": {"type": "string", "minLength": 2},
                "state": {"type": "string", "minLength": 2, "maxLength": 2},
                "lat": {"type": "number"},
                "lng": {"type": "number"},
                "city": {"type": "string"},
                "land_use_type": {
                    "type": "string",
                    "enum": [
                        "vacant_residential",
                        "vacant_commercial",
                        "single_family",
                        "multifamily",
                        "commercial",
                        "industrial",
                        "agricultural",
                    ],
                },
                "min_lot_size_sqft": {"type": "number"},
                "max_lot_size_sqft": {"type": "number"},
                "min_sale_price": {"type": "number"},
                "max_sale_price": {"type": "number"},
                "min_assessed_value": {"type": "number"},
                "max_assessed_value": {"type": "number"},
                "year_built_before": {"type": "integer"},
                "year_built_after": {"type": "integer"},
                "owner_name_contains": {"type": "string"},
                "ownership_min_years": {"type": "integer", "minimum": 0},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 2000},
            },
            "required": ["county"],
        },
        output_schema={"type": "object"},
        budget_cents=50,
    ),
    "filter_dataset": ToolContract(
        name="filter_dataset",
        description="Filter/sort the in-session dataset.",
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    ),
    "get_dataset_info": ToolContract(
        name="get_dataset_info",
        description="Return summary and schema info for the in-session dataset.",
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    ),
    "export_dataset": ToolContract(
        name="export_dataset",
        description="Export dataset to Google Sheets (external write).",
        risk_class=ToolRiskClass.WRITE_EXTERNAL,
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "include_fields": {"type": "array", "items": {"type": "string"}},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "spreadsheet_url": {"type": "string"},
                "title": {"type": "string"},
                "row_count": {"type": "integer"},
            },
            "required": ["status"],
        },
    ),
}
