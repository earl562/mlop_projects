from __future__ import annotations

from plotlot.land_use.models import ToolContract, ToolRiskClass


LOOKUP_EVAL_TOOL_CONTRACTS: dict[str, ToolContract] = {
    "run_lookup_golden_eval_batch": ToolContract(
        name="run_lookup_golden_eval_batch",
        description=(
            "Run recorded lookup snapshots against canonical golden fixtures and persist "
            "the deterministic lookup-correctness eval batch."
        ),
        risk_class=ToolRiskClass.READ_ONLY,
        input_schema={
            "type": "object",
            "properties": {
                "suite": {"type": "string", "minLength": 1},
                "snapshots": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "snapshot_id": {"type": "string", "minLength": 1},
                            "address": {"type": "string", "minLength": 1},
                            "case_id": {"type": "string", "minLength": 1},
                        },
                        "required": ["snapshot_id"],
                    },
                },
                "use_latest_baseline": {"type": "boolean"},
            },
            "required": ["snapshots"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "status": {"type": "string"},
                "suite": {"type": "string"},
                "metrics": {"type": "object"},
                "baseline": {"type": ["object", "null"]},
                "metric_deltas": {"type": ["object", "null"]},
                "gate_failures": {"type": "array"},
                "improvement_log": {"type": "array"},
                "case_results": {"type": "array"},
                "message": {"type": "string"},
                "evidence": {"type": "array"},
            },
            "required": ["status"],
        },
    )
}
