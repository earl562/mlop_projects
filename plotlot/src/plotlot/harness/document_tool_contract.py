from __future__ import annotations

from plotlot.land_use.models import ToolContract, ToolRiskClass


DOCUMENT_TOOL_CONTRACTS: dict[str, ToolContract] = {
    "generate_document": ToolContract(
        name="generate_document",
        description="Generate an internal report/document artifact (no external write).",
        risk_class=ToolRiskClass.WRITE_INTERNAL,
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "evidence_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["evidence_ids"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "artifacts": {"type": "object"},
            },
            "required": ["status"],
        },
    ),
    "draft_google_doc": ToolContract(
        name="draft_google_doc",
        description="Draft a document inside PlotLot (no external write).",
        risk_class=ToolRiskClass.WRITE_INTERNAL,
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string", "minLength": 1},
                "content": {"type": "string"},
                "evidence_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "draft": {"type": "object"},
                "artifacts": {"type": "object"},
            },
            "required": ["status"],
        },
    ),
    "draft_email": ToolContract(
        name="draft_email",
        description="Draft an outreach email inside PlotLot (no external write).",
        risk_class=ToolRiskClass.WRITE_INTERNAL,
        input_schema={
            "type": "object",
            "properties": {
                "to": {"type": "array", "items": {"type": "string"}},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "evidence_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["to", "subject", "body"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "draft": {"type": "object"},
                "artifacts": {"type": "object"},
            },
            "required": ["status"],
        },
    ),
    "gmail_send_draft": ToolContract(
        name="gmail_send_draft",
        description="Send an email draft via Gmail (external write; approval required).",
        risk_class=ToolRiskClass.WRITE_EXTERNAL,
        input_schema={
            "type": "object",
            "properties": {
                "draft_id": {"type": "string", "minLength": 1},
            },
            "required": ["draft_id"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "result": {"type": "object"},
                "message": {"type": "string"},
            },
            "required": ["status"],
        },
    ),
    "create_spreadsheet": ToolContract(
        name="create_spreadsheet",
        description="Create a Google Sheets spreadsheet (external write).",
        risk_class=ToolRiskClass.WRITE_EXTERNAL,
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string", "minLength": 1},
                "headers": {"type": "array", "items": {"type": "string"}},
                "rows": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "string"}},
                },
            },
            "required": ["title", "headers", "rows"],
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
    "create_document": ToolContract(
        name="create_document",
        description="Create a Google Docs document (external write).",
        risk_class=ToolRiskClass.WRITE_EXTERNAL,
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string", "minLength": 1},
                "content": {"type": "string"},
            },
            "required": ["title", "content"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "document_url": {"type": "string"},
                "title": {"type": "string"},
            },
            "required": ["status"],
        },
    ),
}
