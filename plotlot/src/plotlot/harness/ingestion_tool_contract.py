from __future__ import annotations

from plotlot.land_use.models import ToolContract, ToolRiskClass

INGESTION_TOOL_CONTRACTS: dict[str, ToolContract] = {
    "ingest_municipality": ToolContract(
        name="ingest_municipality",
        description=(
            "Ingest official zoning/code text for a municipality into the evidence-backed "
            "ordinance index."
        ),
        risk_class=ToolRiskClass.EXPENSIVE_READ,
        input_schema={
            "type": "object",
            "properties": {
                "municipality": {"type": "string", "minLength": 2},
                "state": {"type": "string", "minLength": 2, "maxLength": 2},
                "county": {"type": "string"},
            },
            "required": ["municipality", "state"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "municipality": {"type": "string"},
                "state": {"type": "string"},
                "county": {"type": ["string", "null"]},
                "chunks_stored": {"type": "integer"},
                "evidence_ids": {"type": "array", "items": {"type": "string"}},
                "quality_flags": {"type": "array", "items": {"type": "string"}},
                "source_record_count": {"type": "integer"},
                "progress": {"type": "array"},
                "message": {"type": "string"},
            },
            "required": [
                "status",
                "municipality",
                "state",
                "chunks_stored",
                "evidence_ids",
                "quality_flags",
                "source_record_count",
                "progress",
            ],
        },
        budget_cents=75,
    )
}
