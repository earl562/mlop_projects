import type { HarnessRunResultData } from "@/lib/api";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface AnalysisLifecycleRecordData {
  readonly id: string;
  readonly workspace_id: string;
  readonly project_id: string;
  readonly site_id?: string | null;
  readonly name: string;
  readonly skill_name: string;
  readonly status: string;
  readonly metadata_json: Record<string, unknown>;
}

export interface CreateAnalysisLifecycleRequest {
  readonly workspaceId: string;
  readonly projectId: string;
  readonly siteId?: string;
  readonly name: string;
  readonly skillName: string;
  readonly metadata?: Record<string, unknown>;
}

export interface LifecycleAwareHarnessRunRequest {
  readonly address: string;
  readonly analysisType: string;
  readonly sourceMode: "fixture" | "live";
  readonly assumptions: Record<string, number | string | boolean>;
  readonly workspaceId?: string;
  readonly projectId?: string;
  readonly siteId?: string;
  readonly analysisId?: string;
}

function errorMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string" && detail.trim()) {
    return detail;
  }
  return fallback;
}

export async function createAnalysisLifecycleRecord(
  request: CreateAnalysisLifecycleRequest,
): Promise<AnalysisLifecycleRecordData> {
  const response = await fetch(`${API_BASE}/api/v1/analyses`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      workspace_id: request.workspaceId,
      project_id: request.projectId,
      site_id: request.siteId,
      name: request.name,
      skill_name: request.skillName,
      metadata_json: request.metadata ?? {},
    }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: "Analysis creation failed" }));
    throw new Error(errorMessage(err.detail, "Analysis creation failed"));
  }
  return response.json() as Promise<AnalysisLifecycleRecordData>;
}

export async function runLifecycleAwareHarnessAnalysis(
  request: LifecycleAwareHarnessRunRequest,
): Promise<HarnessRunResultData> {
  const response = await fetch(`${API_BASE}/api/v1/deal-analysis/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      address: request.address,
      analysisType: request.analysisType,
      sourceMode: request.sourceMode,
      assumptions: request.assumptions,
      workspaceId: request.workspaceId,
      projectId: request.projectId,
      siteId: request.siteId,
      analysisId: request.analysisId,
    }),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ detail: "Harness run failed" }));
    throw new Error(errorMessage(err.detail, "Harness run failed"));
  }
  return response.json() as Promise<HarnessRunResultData>;
}
