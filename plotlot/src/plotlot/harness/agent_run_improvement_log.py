from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal

from plotlot.pipeline.lookup_snapshot_json import JsonValue

type AgentRunImprovementDirection = Literal["improved", "regressed", "flat"]

AGENT_RUN_IMPROVEMENT_LOG_SOURCE: Final = "agent_run_eval"
AGENT_RUN_REGRESSION_RISK: Final = "agent_run_regression_requires_review"
AGENT_RUN_EVAL_METRIC_KEYS: Final = (
    "evidence_coverage",
    "source_quality_traceability",
    "calculation_lineage_traceability",
    "trace_replayability",
    "specialist_lane_coverage",
    "artifact_citation_coverage",
    "assumption_label_coverage",
    "escalation_visibility",
    "ready_for_synthesis_gate",
    "unsupported_claim_rate",
)
LOWER_IS_BETTER_METRIC_KEYS: Final = ("unsupported_claim_rate",)
EPSILON: Final = 1e-12


@dataclass(frozen=True, slots=True)
class AgentRunImprovementLogEntry:
    source: str
    researched_input: str
    changed_rule: str
    metric: str
    direction: AgentRunImprovementDirection
    reason: str
    affected_golden_cases: tuple[str, ...]
    before_score: float
    after_score: float
    delta: float
    gate_blocking: bool
    unresolved_risk: str | None


@dataclass(frozen=True, slots=True)
class AgentRunImprovementLogInput:
    researched_input: str
    affected_golden_cases: tuple[str, ...]
    current_status: str
    current_metrics: Mapping[str, JsonValue]
    previous_metrics: Mapping[str, JsonValue] | None


@dataclass(frozen=True, slots=True)
class _MetricMovement:
    metric: str
    current: float
    baseline: float
    delta: float


def agent_run_metric_deltas(
    current_metrics: Mapping[str, JsonValue],
    previous_metrics: Mapping[str, JsonValue] | None,
) -> dict[str, float]:
    if previous_metrics is None:
        return {}
    deltas: dict[str, float] = {}
    for key in AGENT_RUN_EVAL_METRIC_KEYS:
        current_value = _metric_number(current_metrics, key)
        previous_value = _metric_number(previous_metrics, key)
        if current_value is not None and previous_value is not None:
            deltas[key] = current_value - previous_value
    return deltas


def improved_agent_run_metric_keys(deltas: Mapping[str, float]) -> tuple[str, ...]:
    return tuple(key for key, delta in deltas.items() if _is_metric_improvement(key, delta))


def regressed_agent_run_metric_keys(deltas: Mapping[str, float]) -> tuple[str, ...]:
    return tuple(key for key, delta in deltas.items() if _is_metric_regression(key, delta))


def agent_run_improvement_log_from_metrics(
    log_input: AgentRunImprovementLogInput,
) -> tuple[AgentRunImprovementLogEntry, ...]:
    if log_input.previous_metrics is None:
        return ()
    return tuple(
        _log_entry(log_input, movement)
        for movement in _metric_movements(
            log_input.current_metrics,
            log_input.previous_metrics,
        )
    )


def agent_run_improvement_log_entries_to_json(
    entries: tuple[AgentRunImprovementLogEntry, ...],
) -> list[JsonValue]:
    entries_json: list[JsonValue] = []
    for entry in entries:
        entry_json: dict[str, JsonValue] = {
            "source": entry.source,
            "researched_input": entry.researched_input,
            "changed_rule": entry.changed_rule,
            "metric": entry.metric,
            "direction": entry.direction,
            "reason": entry.reason,
            "affected_golden_cases": list(entry.affected_golden_cases),
            "before_score": entry.before_score,
            "after_score": entry.after_score,
            "delta": entry.delta,
            "gate_blocking": entry.gate_blocking,
            "unresolved_risk": entry.unresolved_risk,
        }
        entries_json.append(entry_json)
    return entries_json


def _log_entry(
    log_input: AgentRunImprovementLogInput,
    movement: _MetricMovement,
) -> AgentRunImprovementLogEntry:
    direction = _direction(movement.metric, movement.delta)
    gate_blocking = direction == "regressed"
    return AgentRunImprovementLogEntry(
        source=AGENT_RUN_IMPROVEMENT_LOG_SOURCE,
        researched_input=log_input.researched_input,
        changed_rule=f"eval_metric:{movement.metric}",
        metric=movement.metric,
        direction=direction,
        reason=_reason(movement.delta),
        affected_golden_cases=log_input.affected_golden_cases,
        before_score=movement.baseline,
        after_score=movement.current,
        delta=movement.delta,
        gate_blocking=gate_blocking,
        unresolved_risk=AGENT_RUN_REGRESSION_RISK if gate_blocking else None,
    )


def _metric_movements(
    current_metrics: Mapping[str, JsonValue],
    previous_metrics: Mapping[str, JsonValue],
) -> tuple[_MetricMovement, ...]:
    movements: list[_MetricMovement] = []
    for key in AGENT_RUN_EVAL_METRIC_KEYS:
        current_value = _metric_number(current_metrics, key)
        previous_value = _metric_number(previous_metrics, key)
        if current_value is not None and previous_value is not None:
            movements.append(
                _MetricMovement(
                    metric=key,
                    current=current_value,
                    baseline=previous_value,
                    delta=current_value - previous_value,
                )
            )
    return tuple(movements)


def _metric_number(metrics: Mapping[str, JsonValue], key: str) -> float | None:
    value = metrics.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _is_metric_improvement(key: str, delta: float) -> bool:
    if key in LOWER_IS_BETTER_METRIC_KEYS:
        return delta < 0
    return delta > 0


def _is_metric_regression(key: str, delta: float) -> bool:
    if key in LOWER_IS_BETTER_METRIC_KEYS:
        return delta > 0
    return delta < 0


def _direction(metric: str, delta: float) -> AgentRunImprovementDirection:
    if abs(delta) <= EPSILON:
        return "flat"
    if metric in LOWER_IS_BETTER_METRIC_KEYS:
        return "improved" if delta < 0 else "regressed"
    return "improved" if delta > 0 else "regressed"


def _reason(delta: float) -> str:
    if abs(delta) <= EPSILON:
        return "baseline_unchanged"
    return "baseline_delta"
