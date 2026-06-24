from __future__ import annotations

from plotlot.land_use.models import ToolContract, ToolRiskClass


LOOKUP_EVAL_HISTORY_TOOL_CONTRACTS: dict[str, ToolContract] = {
    "list_lookup_eval_runs": ToolContract(
        name="list_lookup_eval_runs",
        description=(
            "List recorded lookup-correctness eval runs with metrics, gate failures, "
            "and continuous-improvement log entries."
        ),
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "suite": {"type": "string", "minLength": 1},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "suite": {"type": "string"},
                "run_count": {"type": "integer"},
                "runs": {"type": "array"},
                "evidence": {"type": "array"},
            },
            "required": ["status", "runs", "run_count"],
        },
    ),
    "assess_lookup_release_gate": ToolContract(
        name="assess_lookup_release_gate",
        description=(
            "Assess whether the latest recorded lookup-correctness eval run permits "
            "release or blocks on missing history, failed status, or regression gates."
        ),
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "suite": {"type": "string", "minLength": 1},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "suite": {"type": "string"},
                "decision": {"type": "string"},
                "release_blocked": {"type": "boolean"},
                "reason": {"type": "string"},
                "latest_run": {"type": ["object", "null"]},
                "blockers": {"type": "array"},
                "evidence": {"type": "array"},
            },
            "required": ["status", "decision", "release_blocked", "blockers"],
        },
    ),
}
