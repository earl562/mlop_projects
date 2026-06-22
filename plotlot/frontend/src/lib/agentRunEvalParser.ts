export type AgentRunEvalMetrics = {
  readonly evidence_coverage: number;
  readonly source_quality_traceability: number;
  readonly calculation_lineage_traceability: number;
  readonly trace_replayability: number;
  readonly specialist_lane_coverage: number;
  readonly artifact_citation_coverage: number;
  readonly opportunity_hypothesis_completeness: number;
  readonly assumption_label_coverage: number;
  readonly escalation_visibility: number;
  readonly ready_for_synthesis_gate: number;
  readonly unsupported_claim_rate: number;
};

export type AgentRunEvalRecord = {
  readonly run_id: string;
  readonly lookup_snapshot_id: string;
  readonly eval_run_id: string;
  readonly eval_case_result_id: string;
  readonly status: string;
  readonly metrics: AgentRunEvalMetrics;
};

export type AgentRunImprovementSummary = {
  readonly current: AgentRunEvalRecord;
  readonly previous: AgentRunEvalRecord | null;
  readonly baseline_status: "available" | "missing";
  readonly improvement_status: "improved" | "regressed" | "flat" | "no_baseline";
  readonly release_blocked: boolean;
  readonly deltas: Readonly<Record<string, number>>;
  readonly improved_metric_keys: readonly string[];
  readonly regressed_metric_keys: readonly string[];
};

type JsonRecord = Record<string, unknown>;

export function parseEvalRecord(payload: unknown): AgentRunEvalRecord {
  const record = expectRecord(payload, "agent run eval");
  return {
    run_id: expectString(record, "run_id"),
    lookup_snapshot_id: expectString(record, "lookup_snapshot_id"),
    eval_run_id: expectString(record, "eval_run_id"),
    eval_case_result_id: expectString(record, "eval_case_result_id"),
    status: expectString(record, "status"),
    metrics: parseMetrics(record.metrics),
  };
}

export function parseImprovementSummary(payload: unknown): AgentRunImprovementSummary {
  const record = expectRecord(payload, "agent run improvement summary");
  return {
    current: parseEvalRecord(record.current),
    previous: record.previous === null ? null : parseEvalRecord(record.previous),
    baseline_status: parseBaselineStatus(record.baseline_status),
    improvement_status: parseImprovementStatus(record.improvement_status),
    release_blocked: expectBoolean(record, "release_blocked"),
    deltas: numberRecord(record.deltas),
    improved_metric_keys: stringArray(record.improved_metric_keys),
    regressed_metric_keys: stringArray(record.regressed_metric_keys),
  };
}

function parseMetrics(value: unknown): AgentRunEvalMetrics {
  const record = expectRecord(value, "agent run eval metrics");
  return {
    evidence_coverage: expectNumber(record, "evidence_coverage"),
    source_quality_traceability: expectNumber(record, "source_quality_traceability"),
    calculation_lineage_traceability: expectNumber(
      record,
      "calculation_lineage_traceability",
    ),
    trace_replayability: expectNumber(record, "trace_replayability"),
    specialist_lane_coverage: expectNumber(record, "specialist_lane_coverage"),
    artifact_citation_coverage: expectNumber(record, "artifact_citation_coverage"),
    opportunity_hypothesis_completeness: expectNumber(
      record,
      "opportunity_hypothesis_completeness",
    ),
    assumption_label_coverage: expectNumber(record, "assumption_label_coverage"),
    escalation_visibility: expectNumber(record, "escalation_visibility"),
    ready_for_synthesis_gate: expectNumber(record, "ready_for_synthesis_gate"),
    unsupported_claim_rate: expectNumber(record, "unsupported_claim_rate"),
  };
}

function parseBaselineStatus(value: unknown): "available" | "missing" {
  if (value === "available" || value === "missing") return value;
  throw new Error("Invalid agent run baseline status");
}

function parseImprovementStatus(
  value: unknown,
): "improved" | "regressed" | "flat" | "no_baseline" {
  if (
    value === "improved" ||
    value === "regressed" ||
    value === "flat" ||
    value === "no_baseline"
  ) {
    return value;
  }
  throw new Error("Invalid agent run improvement status");
}

function expectRecord(value: unknown, label: string): JsonRecord {
  if (typeof value === "object" && value !== null && !Array.isArray(value)) {
    return Object.fromEntries(Object.entries(value));
  }
  throw new Error(`Invalid ${label} payload`);
}

function expectString(record: JsonRecord, key: string): string {
  const value = record[key];
  if (typeof value === "string") return value;
  throw new Error(`Expected string field ${key}`);
}

function expectBoolean(record: JsonRecord, key: string): boolean {
  const value = record[key];
  if (typeof value === "boolean") return value;
  throw new Error(`Expected boolean field ${key}`);
}

function expectNumber(record: JsonRecord, key: string): number {
  const value = record[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  throw new Error(`Expected number field ${key}`);
}

function stringArray(value: unknown): readonly string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item) => typeof item === "string");
}

function numberRecord(value: unknown): Readonly<Record<string, number>> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return {};
  const parsed: Record<string, number> = {};
  for (const [key, item] of Object.entries(value)) {
    if (typeof item === "number" && Number.isFinite(item)) {
      parsed[key] = item;
    }
  }
  return parsed;
}
