import { parseAgentRunTrace } from "./agentRunTraceParser";
import type { AgentRunTraceData } from "./agentRunTraceTypes";

export type {
  AgentRunTraceAssignment,
  AgentRunTraceArtifact,
  AgentRunTraceData,
  AgentRunTraceEval,
  AgentRunTraceEvidencePacket,
  AgentRunTraceImprovement,
  AgentRunTraceOpportunity,
  AgentRunTraceReportClaim,
  AgentRunTraceReportSection,
  AgentRunTraceSourceRetrieval,
  AgentRunTraceStep,
} from "./agentRunTraceTypes";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

class AgentRunTraceHttpError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "AgentRunTraceHttpError";
    this.status = status;
  }
}

export async function fetchAgentRunTrace(
  runId: string,
  workspaceId: string,
): Promise<AgentRunTraceData> {
  const response = await fetch(
    `${API_BASE}/api/v1/agent-runs/${encodeURIComponent(runId)}/trace?workspace_id=${encodeURIComponent(workspaceId)}`,
    { cache: "no-store" },
  );
  const payload = await responseJson(response, "Agent run trace retrieval failed");
  return parseAgentRunTrace(payload);
}

async function responseJson(response: Response, fallback: string): Promise<unknown> {
  let payload: unknown;
  try {
    payload = await response.json();
  } catch (caught) {
    if (caught instanceof SyntaxError) {
      payload = { detail: fallback };
    } else {
      throw caught;
    }
  }
  if (!response.ok) {
    throw new AgentRunTraceHttpError(extractDetail(payload, response.status), response.status);
  }
  return payload;
}

function extractDetail(payload: unknown, status: number): string {
  if (typeof payload === "object" && payload !== null && !Array.isArray(payload)) {
    const detail = Object.fromEntries(Object.entries(payload)).detail;
    if (typeof detail === "string") return detail;
  }
  return `HTTP ${status}`;
}
