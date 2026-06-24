import {
  parseEvalRecord,
  parseImprovementSummary,
  type AgentRunEvalRecord,
  type AgentRunImprovementSummary,
} from "./agentRunEvalParser";

export type {
  AgentRunEvalMetrics,
  AgentRunEvalRecord,
  AgentRunImprovementSummary,
} from "./agentRunEvalParser";

export type LookupSnapshotFieldData = {
  readonly key: string;
  readonly label: string;
  readonly value: string | number | boolean | null;
  readonly unit: string;
  readonly display_state: string;
  readonly evidence_ids: readonly string[];
  readonly source_priority: readonly string[];
  readonly fallback_sources: readonly string[];
  readonly failure_behavior: string;
  readonly confidence: number;
  readonly freshness: string;
  readonly warnings: readonly string[];
};

export type LookupSnapshotCalculationData = {
  readonly calculator_name: string;
  readonly calculator_version: string;
  readonly formula: string;
  readonly input_evidence_ids: readonly string[];
  readonly output_label: string;
  readonly warnings: readonly string[];
};

export type LookupSnapshotSourceMetadataData = {
  readonly evidence_id: string;
  readonly source_url: string;
  readonly source_title: string;
  readonly effective_date: string;
};

export type LookupSnapshotData = {
  readonly lookup_snapshot_id: string;
  readonly site_id: string;
  readonly run_id: string;
  readonly fields: readonly LookupSnapshotFieldData[];
  readonly calculations: readonly LookupSnapshotCalculationData[];
  readonly warnings: readonly string[];
  readonly source_metadata: readonly LookupSnapshotSourceMetadataData[];
};

export type AgentRunStartParams = {
  readonly lookupSnapshotId: string;
  readonly objective: string;
  readonly workspaceId?: string;
  readonly projectId?: string;
};

export type AgentRunResponseData = {
  readonly run_id: string;
  readonly lookup_snapshot_id: string;
  readonly workspace_id: string;
  readonly status: string;
  readonly evidence_ids: readonly string[];
  readonly warnings: readonly string[];
  readonly ready_for_synthesis: boolean;
};

type JsonRecord = Record<string, unknown>;

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export const DEFAULT_AGENT_RUN_WORKSPACE_ID = "frontend_workspace";

export async function startAgentRun(
  params: AgentRunStartParams,
): Promise<AgentRunResponseData> {
  const workspaceId = params.workspaceId ?? DEFAULT_AGENT_RUN_WORKSPACE_ID;
  const response = await fetch(`${API_BASE}/api/v1/agent-runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      lookup_snapshot_id: params.lookupSnapshotId,
      workspace_id: workspaceId,
      project_id: params.projectId ?? "frontend_project",
      objective: params.objective,
    }),
  });
  const payload = await responseJson(response, "Agent run start failed");
  return parseAgentRunResponse(payload);
}

export async function evaluateAgentRun(
  runId: string,
  workspaceId: string,
): Promise<AgentRunEvalRecord> {
  const response = await fetch(
    `${API_BASE}/api/v1/agent-runs/${encodeURIComponent(runId)}/evals?workspace_id=${encodeURIComponent(workspaceId)}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    },
  );
  const payload = await responseJson(response, "Agent run eval failed");
  return parseEvalRecord(payload);
}

export async function fetchAgentRunImprovementSummary(
  runId: string,
  workspaceId: string,
): Promise<AgentRunImprovementSummary> {
  const response = await fetch(
    `${API_BASE}/api/v1/agent-runs/${encodeURIComponent(runId)}/improvement-summary?workspace_id=${encodeURIComponent(workspaceId)}`,
    { cache: "no-store" },
  );
  const payload = await responseJson(response, "Agent run improvement summary failed");
  return parseImprovementSummary(payload);
}

async function responseJson(response: Response, fallback: string): Promise<unknown> {
  const payload: unknown = await response.json().catch(() => ({ detail: fallback }));
  if (!response.ok) {
    throw new Error(extractDetail(payload, response.status));
  }
  return payload;
}

function parseAgentRunResponse(payload: unknown): AgentRunResponseData {
  const record = expectRecord(payload, "agent run response");
  return {
    run_id: expectString(record, "run_id"),
    lookup_snapshot_id: expectString(record, "lookup_snapshot_id"),
    workspace_id: expectString(record, "workspace_id"),
    status: expectString(record, "status"),
    evidence_ids: stringArray(record.evidence_ids),
    warnings: stringArray(record.warnings),
    ready_for_synthesis: expectBoolean(record, "ready_for_synthesis"),
  };
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

function stringArray(value: unknown): readonly string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item) => typeof item === "string");
}

function extractDetail(payload: unknown, status: number): string {
  if (typeof payload === "object" && payload !== null && !Array.isArray(payload)) {
    const detail = Object.fromEntries(Object.entries(payload)).detail;
    if (typeof detail === "string") return detail;
  }
  return `HTTP ${status}`;
}
