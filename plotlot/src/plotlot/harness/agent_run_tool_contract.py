from __future__ import annotations

from plotlot.land_use.models import ToolContract, ToolRiskClass


AGENT_RUN_TOOL_CONTRACTS: dict[str, ToolContract] = {
    "start_agent_run": ToolContract(
        name="start_agent_run",
        description=(
            "Start a replayable specialist-lane agent run from a recorded lookup snapshot."
        ),
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "lookup_snapshot_id": {"type": "string", "minLength": 1},
                "objective": {"type": "string", "minLength": 1},
                "open_questions": {"type": "array", "items": {"type": "string"}},
                "warnings": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["lookup_snapshot_id", "objective"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "run": {"type": "object"},
                "evidence": {"type": "array"},
                "evidence_ids": {"type": "array", "items": {"type": "string"}},
                "evidence_packets": {"type": "array"},
                "message": {"type": "string"},
            },
            "required": ["status"],
        },
    ),
    "get_agent_run_trace": ToolContract(
        name="get_agent_run_trace",
        description=(
            "Return the replayable trace package for an agent run, including plan, "
            "artifact, latest eval, and improvement gate checkpoints."
        ),
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {"run_id": {"type": "string", "minLength": 1}},
            "required": ["run_id"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "trace": {"type": "object"},
                "evidence": {"type": "array"},
                "evidence_ids": {"type": "array", "items": {"type": "string"}},
                "evidence_packets": {"type": "array"},
                "message": {"type": "string"},
            },
            "required": ["status"],
        },
    ),
}
