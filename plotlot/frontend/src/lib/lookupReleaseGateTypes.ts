export type LookupReleaseGateDecision = "blocked" | "passed";

export type LookupReleaseGateBlocker = {
  readonly code: string;
  readonly message: string;
  readonly metric: string | null;
  readonly reason: string | null;
  readonly status: string | null;
  readonly current: number | null;
  readonly baseline: number | null;
};

export type LookupReleaseGateFailure = {
  readonly metric: string;
  readonly reason: string | null;
  readonly current: number | null;
  readonly baseline: number | null;
};

export type LookupReleaseGateImprovementEntry = {
  readonly source: string | null;
  readonly researched_input: string | null;
  readonly changed_rule: string;
  readonly metric: string | null;
  readonly direction: string | null;
  readonly reason: string | null;
  readonly affected_golden_cases: readonly string[];
  readonly before_score: number | null;
  readonly after_score: number | null;
  readonly delta: number | null;
  readonly gate_blocking: boolean | null;
  readonly unresolved_risk: string | null;
};

export type LookupReleaseGateRun = {
  readonly eval_run_id: string;
  readonly suite: string;
  readonly status: string;
  readonly created_at: string | null;
  readonly completed_at: string | null;
  readonly metrics: Readonly<Record<string, number>>;
  readonly baseline: Readonly<Record<string, number>> | null;
  readonly metric_deltas: Readonly<Record<string, number>> | null;
  readonly gate_failures: readonly LookupReleaseGateFailure[];
  readonly improvement_log: readonly LookupReleaseGateImprovementEntry[];
  readonly case_ids: readonly string[];
  readonly lookup_snapshot_ids: readonly string[];
};

export type LookupReleaseGateData = {
  readonly status: string;
  readonly suite: string;
  readonly decision: LookupReleaseGateDecision;
  readonly release_blocked: boolean;
  readonly reason: string;
  readonly latest_run: LookupReleaseGateRun | null;
  readonly blockers: readonly LookupReleaseGateBlocker[];
  readonly evidence: readonly string[];
};

export type LookupGoldenEvalBatchItem = {
  readonly snapshot_id: string;
  readonly address?: string;
  readonly case_id?: string;
};

export type LookupGoldenEvalBatchRequest = {
  readonly suite?: string;
  readonly snapshots: readonly LookupGoldenEvalBatchItem[];
  readonly use_latest_baseline?: boolean;
};

export type LookupEvalBatchCaseResult = {
  readonly lookup_snapshot_id: string;
  readonly case_id: string;
  readonly status: string;
};

export type LookupEvalBatchResult = {
  readonly suite: string;
  readonly status: string;
  readonly metrics: Readonly<Record<string, number>>;
  readonly baseline: Readonly<Record<string, number>> | null;
  readonly metric_deltas: Readonly<Record<string, number>> | null;
  readonly gate_failures: readonly LookupReleaseGateFailure[];
  readonly improvement_log: readonly LookupReleaseGateImprovementEntry[];
  readonly case_results: readonly LookupEvalBatchCaseResult[];
};
