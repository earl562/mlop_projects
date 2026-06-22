import type {
  LookupEvalBatchCaseResult,
  LookupEvalBatchResult,
  LookupGoldenEvalBatchRequest,
  LookupReleaseGateBlocker,
  LookupReleaseGateData,
  LookupReleaseGateDecision,
  LookupReleaseGateFailure,
  LookupReleaseGateImprovementEntry,
  LookupReleaseGateRun,
} from "./lookupReleaseGateTypes";

export type {
  LookupEvalBatchCaseResult,
  LookupEvalBatchResult,
  LookupGoldenEvalBatchItem,
  LookupGoldenEvalBatchRequest,
  LookupReleaseGateBlocker,
  LookupReleaseGateData,
  LookupReleaseGateDecision,
  LookupReleaseGateFailure,
  LookupReleaseGateImprovementEntry,
  LookupReleaseGateRun,
} from "./lookupReleaseGateTypes";

type JsonRecord = Record<string, unknown>;

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export async function fetchLookupReleaseGate(
  suite = "lookup_correctness",
): Promise<LookupReleaseGateData> {
  const query = new URLSearchParams({ suite });
  const response = await fetch(
    `${API_BASE}/api/v1/lookup-snapshots/evals/batch/release-gate?${query.toString()}`,
    { cache: "no-store" },
  );
  const payload = await responseJson(response, "Lookup release gate request failed");
  return parseLookupReleaseGate(payload);
}

export async function runLookupGoldenEvalBatch(
  request: LookupGoldenEvalBatchRequest,
): Promise<LookupEvalBatchResult> {
  const response = await fetch(`${API_BASE}/api/v1/lookup-snapshots/evals/batch/golden`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      suite: request.suite ?? "lookup_correctness",
      snapshots: request.snapshots,
      use_latest_baseline: request.use_latest_baseline ?? true,
    }),
  });
  const payload = await responseJson(response, "Lookup golden eval request failed");
  return parseLookupEvalBatchResult(payload);
}

async function responseJson(response: Response, fallback: string): Promise<unknown> {
  const payload: unknown = await response.json().catch(() => ({ detail: fallback }));
  if (!response.ok) {
    throw new Error(extractDetail(payload, response.status));
  }
  return payload;
}

function parseLookupReleaseGate(payload: unknown): LookupReleaseGateData {
  const record = expectRecord(payload, "lookup release gate");
  return {
    status: expectString(record, "status"),
    suite: expectString(record, "suite"),
    decision: parseDecision(record.decision),
    release_blocked: expectBoolean(record, "release_blocked"),
    reason: expectString(record, "reason"),
    latest_run: parseNullableRun(record.latest_run),
    blockers: recordArray(record.blockers).map(parseBlocker),
    evidence: stringArray(record.evidence),
  };
}

function parseLookupEvalBatchResult(payload: unknown): LookupEvalBatchResult {
  const record = expectRecord(payload, "lookup eval batch result");
  return {
    suite: expectString(record, "suite"),
    status: expectString(record, "status"),
    metrics: numberRecord(record.metrics),
    baseline: optionalNumberRecord(record.baseline),
    metric_deltas: optionalNumberRecord(record.metric_deltas),
    gate_failures: recordArray(record.gate_failures).map(parseFailure),
    improvement_log: recordArray(record.improvement_log).map(parseImprovementEntry),
    case_results: recordArray(record.case_results).map(parseBatchCaseResult),
  };
}

function parseNullableRun(value: unknown): LookupReleaseGateRun | null {
  if (value === null) return null;
  const record = expectRecord(value, "lookup release gate run");
  return {
    eval_run_id: expectString(record, "eval_run_id"),
    suite: expectString(record, "suite"),
    status: expectString(record, "status"),
    created_at: optionalString(record, "created_at"),
    completed_at: optionalString(record, "completed_at"),
    metrics: numberRecord(record.metrics),
    baseline: optionalNumberRecord(record.baseline),
    metric_deltas: optionalNumberRecord(record.metric_deltas),
    gate_failures: recordArray(record.gate_failures).map(parseFailure),
    improvement_log: recordArray(record.improvement_log).map(parseImprovementEntry),
    case_ids: stringArray(record.case_ids),
    lookup_snapshot_ids: stringArray(record.lookup_snapshot_ids),
  };
}

function parseBatchCaseResult(record: JsonRecord): LookupEvalBatchCaseResult {
  return {
    lookup_snapshot_id: expectString(record, "lookup_snapshot_id"),
    case_id: expectString(record, "case_id"),
    status: expectString(record, "status"),
  };
}

function parseBlocker(record: JsonRecord): LookupReleaseGateBlocker {
  return {
    code: expectString(record, "code"),
    message: expectString(record, "message"),
    metric: optionalString(record, "metric"),
    reason: optionalString(record, "reason"),
    status: optionalString(record, "status"),
    current: optionalNumber(record, "current"),
    baseline: optionalNumber(record, "baseline"),
  };
}

function parseFailure(record: JsonRecord): LookupReleaseGateFailure {
  return {
    metric: expectString(record, "metric"),
    reason: optionalString(record, "reason"),
    current: optionalNumber(record, "current"),
    baseline: optionalNumber(record, "baseline"),
  };
}

function parseImprovementEntry(record: JsonRecord): LookupReleaseGateImprovementEntry {
  return {
    source: optionalString(record, "source"),
    researched_input: optionalString(record, "researched_input"),
    changed_rule: expectString(record, "changed_rule"),
    metric: optionalString(record, "metric"),
    direction: optionalString(record, "direction"),
    reason: optionalString(record, "reason"),
    affected_golden_cases: stringArray(record.affected_golden_cases),
    before_score: optionalNumber(record, "before_score"),
    after_score: optionalNumber(record, "after_score"),
    delta: optionalNumber(record, "delta"),
    gate_blocking: optionalBoolean(record, "gate_blocking"),
    unresolved_risk: optionalString(record, "unresolved_risk"),
  };
}

function parseDecision(value: unknown): LookupReleaseGateDecision {
  if (value === "blocked" || value === "passed") return value;
  throw new Error("Invalid lookup release gate decision");
}

function expectRecord(value: unknown, label: string): JsonRecord {
  if (typeof value === "object" && value !== null && !Array.isArray(value)) {
    return Object.fromEntries(Object.entries(value));
  }
  throw new Error(`Invalid ${label} payload`);
}

function recordArray(value: unknown): readonly JsonRecord[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => expectRecord(item, "lookup release gate list item"));
}

function expectString(record: JsonRecord, key: string): string {
  const value = record[key];
  if (typeof value === "string") return value;
  throw new Error(`Expected string field ${key}`);
}

function optionalString(record: JsonRecord, key: string): string | null {
  const value = record[key];
  if (value === null || value === undefined) return null;
  if (typeof value === "string") return value;
  throw new Error(`Expected nullable string field ${key}`);
}

function expectBoolean(record: JsonRecord, key: string): boolean {
  const value = record[key];
  if (typeof value === "boolean") return value;
  throw new Error(`Expected boolean field ${key}`);
}

function optionalBoolean(record: JsonRecord, key: string): boolean | null {
  const value = record[key];
  if (value === null || value === undefined) return null;
  if (typeof value === "boolean") return value;
  throw new Error(`Expected nullable boolean field ${key}`);
}

function optionalNumber(record: JsonRecord, key: string): number | null {
  const value = record[key];
  if (value === null || value === undefined) return null;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  throw new Error(`Expected nullable number field ${key}`);
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

function optionalNumberRecord(value: unknown): Readonly<Record<string, number>> | null {
  if (value === null || value === undefined) return null;
  return numberRecord(value);
}

function extractDetail(payload: unknown, status: number): string {
  if (typeof payload === "object" && payload !== null && !Array.isArray(payload)) {
    const detail = Object.fromEntries(Object.entries(payload)).detail;
    if (typeof detail === "string") return detail;
  }
  return `HTTP ${status}`;
}
