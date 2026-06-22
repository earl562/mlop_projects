export function noHistoryPayload() {
  return {
    status: "success",
    suite: "lookup_correctness",
    decision: "blocked",
    release_blocked: true,
    reason: "no_completed_eval_run",
    latest_run: null,
    blockers: [
      {
        code: "missing_eval_history",
        message: "No completed lookup-correctness batch eval run is recorded.",
      },
    ],
    evidence: [],
  };
}

export function blockedPayload() {
  return {
    status: "success",
    suite: "lookup_correctness",
    decision: "blocked",
    release_blocked: true,
    reason: "latest_eval_failed",
    latest_run: {
      eval_run_id: "eval-regressed",
      suite: "lookup_correctness",
      status: "failed",
      created_at: "2026-06-21T14:00:00+00:00",
      completed_at: "2026-06-21T14:00:02+00:00",
      metrics: {
        pass_rate: 0.5,
        citation_coverage: 0.5,
        unsupported_claim_rate: 0,
        deterministic_calculation_reproducibility: 1,
      },
      baseline: { pass_rate: 1 },
      metric_deltas: { pass_rate: -0.5 },
      gate_failures: [
        {
          metric: "pass_rate",
          reason: "regressed",
          current: 0.5,
          baseline: 1,
        },
      ],
      improvement_log: [
        {
          source: "lookup_snapshot_eval_batch",
          researched_input: "lookup_correctness",
          changed_rule: "eval_metric:pass_rate",
          metric: "pass_rate",
          direction: "regressed",
          reason: "baseline_delta",
          affected_golden_cases: ["case-a"],
          before_score: 1,
          after_score: 0.5,
          delta: -0.5,
          gate_blocking: true,
          unresolved_risk: "baseline_regression_requires_review",
        },
      ],
      case_ids: ["case-a"],
      lookup_snapshot_ids: ["ls_case-a"],
    },
    blockers: [
      {
        code: "regression_gate_failed",
        metric: "pass_rate",
        message: "Lookup-correctness regression gate failed for pass_rate.",
        reason: "regressed",
        current: 0.5,
        baseline: 1,
      },
      {
        code: "latest_eval_failed",
        status: "failed",
        message: "Latest lookup-correctness eval run did not pass.",
      },
    ],
    evidence: [],
  };
}

export function passedPayload() {
  return {
    status: "success",
    suite: "lookup_correctness",
    decision: "passed",
    release_blocked: false,
    reason: "latest_eval_passed",
    latest_run: {
      eval_run_id: "eval-pass",
      suite: "lookup_correctness",
      status: "passed",
      created_at: "2026-06-21T14:00:00+00:00",
      completed_at: "2026-06-21T14:00:02+00:00",
      metrics: {
        pass_rate: 1,
        citation_coverage: 1,
        unsupported_claim_rate: 0,
        deterministic_calculation_reproducibility: 1,
      },
      baseline: null,
      metric_deltas: null,
      gate_failures: [],
      improvement_log: [],
      case_ids: ["case-a", "case-b"],
      lookup_snapshot_ids: ["ls_case-a", "ls_case-b"],
    },
    blockers: [],
    evidence: [],
  };
}

export function batchEvalPayload() {
  return {
    suite: "lookup_correctness",
    status: "passed",
    metrics: {
      pass_rate: 1,
      case_count: 1,
      passed_count: 1,
      failed_count: 0,
      field_value_accuracy: 1,
      display_state_accuracy: 1,
      citation_coverage: 1,
      warning_coverage: 1,
      deterministic_calculation_reproducibility: 1,
      unsupported_claim_rate: 0,
    },
    baseline: null,
    metric_deltas: null,
    gate_failures: [],
    improvement_log: [],
    case_results: [
      {
        lookup_snapshot_id: "ls_fixture",
        case_id: "golden-data-171-ne-209th-ter",
        status: "passed",
        metrics: {},
        diffs: {},
      },
    ],
  };
}
