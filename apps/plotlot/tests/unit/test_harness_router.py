"""Gold-set tests for deterministic harness routing."""

from __future__ import annotations

import json
from pathlib import Path

from plotlot.harness.router import IntentRouter


def test_router_gold_cases_are_stable() -> None:
    router = IntentRouter()
    gold_path = Path(__file__).resolve().parents[1] / "gold" / "router_cases.jsonl"
    lines = gold_path.read_text(encoding="utf-8").splitlines()
    assert lines, "router_cases.jsonl must contain at least one case"

    for line in lines:
        case = json.loads(line)
        assert router.route(case["input"]) == case["expected_skill"]
