export const noHistoryReleaseGatePayload = {
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
} as const;

export const passedReleaseGatePayload = {
  status: "success",
  suite: "lookup_correctness",
  decision: "passed",
  release_blocked: false,
  reason: "latest_eval_passed",
  latest_run: {
    eval_run_id: "eval-e2e-pass",
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
    case_ids: ["golden-data-171-ne-209th-ter"],
    lookup_snapshot_ids: ["lookup_e2e_agent_snapshot"],
  },
  blockers: [],
  evidence: [],
} as const;

export const goldenBatchPayload = {
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
      lookup_snapshot_id: "lookup_e2e_agent_snapshot",
      case_id: "golden-data-171-ne-209th-ter",
      status: "passed",
      metrics: {},
      diffs: {},
    },
  ],
} as const;
