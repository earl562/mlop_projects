from __future__ import annotations

from plotlot.land_use.models import ToolContract, ToolRiskClass


AGENT_RUN_EVAL_TOOL_CONTRACTS: dict[str, ToolContract] = {
    "evaluate_agent_run": ToolContract(
        name="evaluate_agent_run",
        description="Score a recorded agent run against deterministic replay/evidence gates.",
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
                "eval": {"type": "object"},
                "evidence": {"type": "array"},
                "message": {"type": "string"},
            },
            "required": ["status"],
        },
    ),
    "get_latest_agent_run_eval": ToolContract(
        name="get_latest_agent_run_eval",
        description="Return the latest persisted deterministic eval for an agent run.",
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
                "eval": {"type": "object"},
                "evidence": {"type": "array"},
                "message": {"type": "string"},
            },
            "required": ["status"],
        },
    ),
    "get_agent_run_improvement_summary": ToolContract(
        name="get_agent_run_improvement_summary",
        description="Return baseline delta and release-blocking status for an agent-run eval.",
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
                "improvement": {"type": "object"},
                "evidence": {"type": "array"},
                "message": {"type": "string"},
            },
            "required": ["status"],
        },
    ),
}
