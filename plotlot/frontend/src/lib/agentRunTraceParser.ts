import type {
  AgentRunTraceArtifact,
  AgentRunTraceAssumption,
  AgentRunTraceAssumptionSource,
  AgentRunTraceAssumptionStatus,
  AgentRunTraceAssignment,
  AgentRunTraceData,
  AgentRunTraceEval,
  AgentRunTraceEvidencePacket,
  AgentRunTraceImprovement,
  AgentRunTraceImprovementLog,
  AgentRunTraceStep,
} from "./agentRunTraceTypes";
import { parseAgentRunOpportunity } from "./agentRunOpportunityParser";
import { parseAgentRunReportSections } from "./agentRunReportSectionParser";
import { parseAgentRunSourceRetrieval } from "./agentRunSourceRetrievalParser";

type JsonRecord = Record<string, unknown>;

class AgentRunTraceParseError extends Error {
  readonly field: string | null;

  constructor(message: string, field: string | null = null) {
    super(message);
    this.name = "AgentRunTraceParseError";
    this.field = field;
  }
}

export function parseAgentRunTrace(payload: unknown): AgentRunTraceData {
  const record = expectRecord(payload, "agent run trace");
  return {
    run_id: expectString(record, "run_id"),
    lookup_snapshot_id: expectString(record, "lookup_snapshot_id"),
    workspace_id: expectString(record, "workspace_id"),
    project_id: optionalString(record, "project_id"),
    site_id: optionalString(record, "site_id"),
    objective: expectString(record, "objective"),
    status: expectString(record, "status"),
    ready_for_synthesis: expectBoolean(record, "ready_for_synthesis"),
    evidence_ids: stringArray(record, "evidence_ids"),
    evidence_packets: recordArray(record.evidence_packets, "agent run evidence packets").map(
      parseEvidencePacket,
    ),
    source_retrievals: recordArray(record.source_retrievals, "agent run source retrievals").map(
      parseAgentRunSourceRetrieval,
    ),
    warnings: stringArray(record, "warnings"),
    open_questions: stringArray(record, "open_questions"),
    assignments: recordArray(record.assignments, "agent run assignments").map(parseAssignment),
    escalations: recordArray(record.escalations, "agent run escalations"),
    trace_steps: recordArray(record.trace_steps, "agent run trace steps").map(parseTraceStep),
    artifact: parseArtifact(record.artifact),
    latest_eval: record.latest_eval === null ? null : parseEval(record.latest_eval),
    improvement: record.improvement === null ? null : parseImprovement(record.improvement),
    replay_ready: expectBoolean(record, "replay_ready"),
    missing_replay_requirements: stringArray(record, "missing_replay_requirements"),
  };
}

function parseEvidencePacket(value: JsonRecord): AgentRunTraceEvidencePacket {
  return {
    evidence_id: expectString(value, "evidence_id"),
    source_type: expectString(value, "source_type"),
    source_authority: expectString(value, "source_authority"),
    source_title: expectString(value, "source_title"),
    source_url: expectString(value, "source_url"),
    retrieved_at: expectString(value, "retrieved_at"),
    effective_date: expectString(value, "effective_date"),
    parser_version: expectString(value, "parser_version"),
    schema_version: expectString(value, "schema_version"),
    raw_artifact_ref: expectString(value, "raw_artifact_ref"),
    referenced_field_keys: stringArray(value, "referenced_field_keys"),
    calculation_outputs: stringArray(value, "calculation_outputs"),
    lineage: stringArray(value, "lineage"),
    confidence: expectNumber(value, "confidence"),
    quality_score: expectNumber(value, "quality_score"),
    quality_flags: stringArray(value, "quality_flags"),
    warnings: stringArray(value, "warnings"),
  };
}

function parseAssignment(value: JsonRecord): AgentRunTraceAssignment {
  return {
    lane: expectString(value, "lane"),
    objective: expectString(value, "objective"),
    field_keys: stringArray(value, "field_keys"),
    evidence_ids: stringArray(value, "evidence_ids"),
    calculation_outputs: stringArray(value, "calculation_outputs"),
    warnings: stringArray(value, "warnings"),
    escalation_required: expectBoolean(value, "escalation_required"),
  };
}

function parseTraceStep(value: JsonRecord): AgentRunTraceStep {
  return {
    sequence: expectNumber(value, "sequence"),
    kind: expectString(value, "kind"),
    summary: expectString(value, "summary"),
    lane: optionalString(value, "lane"),
    field_keys: stringArray(value, "field_keys"),
    evidence_ids: stringArray(value, "evidence_ids"),
    calculation_outputs: stringArray(value, "calculation_outputs"),
    warnings: stringArray(value, "warnings"),
    escalation_required: expectBoolean(value, "escalation_required"),
  };
}

function parseArtifact(value: unknown): AgentRunTraceArtifact {
  const record = expectRecord(value, "agent run trace artifact");
  return {
    status: expectString(record, "status"),
    report_id: optionalString(record, "report_id"),
    document_id: optionalString(record, "document_id"),
    evidence_ids: stringArray(record, "evidence_ids"),
    sections: parseAgentRunReportSections(record.sections),
    opportunities: recordArray(record.opportunities, "agent run opportunities").map(
      parseAgentRunOpportunity,
    ),
    assumptions: recordArray(record.assumptions, "agent run artifact assumptions").map(
      parseAssumption,
    ),
    message: optionalString(record, "message"),
  };
}

function parseAssumption(value: JsonRecord): AgentRunTraceAssumption {
  return {
    key: expectString(value, "key"),
    text: expectString(value, "text"),
    status: parseAssumptionStatus(value.status),
    source: parseAssumptionSource(value.source),
    field_key: optionalString(value, "field_key"),
  };
}

function parseEval(value: unknown): AgentRunTraceEval {
  const record = expectRecord(value, "agent run trace eval");
  return {
    eval_run_id: expectString(record, "eval_run_id"),
    eval_case_result_id: expectString(record, "eval_case_result_id"),
    gold_set_case_id: expectString(record, "gold_set_case_id"),
    status: expectString(record, "status"),
    metric_keys: stringArray(record, "metric_keys"),
    evidence_metric_keys: stringArray(record, "evidence_metric_keys"),
    trajectory_metric_keys: stringArray(record, "trajectory_metric_keys"),
  };
}

function parseImprovement(value: unknown): AgentRunTraceImprovement {
  const record = expectRecord(value, "agent run trace improvement");
  return {
    baseline_status: parseBaselineStatus(record.baseline_status),
    improvement_status: parseImprovementStatus(record.improvement_status),
    release_blocked: expectBoolean(record, "release_blocked"),
    improved_metric_keys: stringArray(record, "improved_metric_keys"),
    regressed_metric_keys: stringArray(record, "regressed_metric_keys"),
    improvement_log: recordArray(record.improvement_log, "agent run improvement log").map(
      parseImprovementLog,
    ),
  };
}

function parseImprovementLog(value: JsonRecord): AgentRunTraceImprovementLog {
  return {
    source: expectString(value, "source"),
    researched_input: expectString(value, "researched_input"),
    changed_rule: expectString(value, "changed_rule"),
    metric: expectString(value, "metric"),
    direction: expectString(value, "direction"),
    reason: expectString(value, "reason"),
    affected_golden_cases: stringArray(value, "affected_golden_cases"),
    before_score: expectNumber(value, "before_score"),
    after_score: expectNumber(value, "after_score"),
    delta: expectNumber(value, "delta"),
    gate_blocking: expectBoolean(value, "gate_blocking"),
    unresolved_risk: optionalString(value, "unresolved_risk"),
  };
}

function parseAssumptionSource(value: unknown): AgentRunTraceAssumptionSource {
  if (
    value === "agent_run.open_question" ||
    value === "agent_run.escalation" ||
    value === "agent_run.warning"
  ) {
    return value;
  }
  throw new AgentRunTraceParseError("Invalid agent run assumption source", "source");
}

function parseAssumptionStatus(value: unknown): AgentRunTraceAssumptionStatus {
  if (value === "requires_human_review" || value === "warning") return value;
  throw new AgentRunTraceParseError("Invalid agent run assumption status", "status");
}

function parseBaselineStatus(value: unknown): "available" | "missing" {
  if (value === "available" || value === "missing") return value;
  throw new AgentRunTraceParseError("Invalid agent run trace baseline status", "baseline_status");
}

function parseImprovementStatus(value: unknown): "improved" | "regressed" | "flat" | "no_baseline" {
  if (
    value === "improved" ||
    value === "regressed" ||
    value === "flat" ||
    value === "no_baseline"
  ) {
    return value;
  }
  throw new AgentRunTraceParseError("Invalid agent run trace improvement status", "improvement_status");
}

function expectRecord(value: unknown, label: string): JsonRecord {
  if (typeof value === "object" && value !== null && !Array.isArray(value)) {
    return Object.fromEntries(Object.entries(value));
  }
  throw new AgentRunTraceParseError(`Invalid ${label} payload`);
}

function recordArray(value: unknown, label: string): readonly JsonRecord[] {
  if (!Array.isArray(value)) throw new AgentRunTraceParseError(`Invalid ${label} payload`);
  return value.map((item) => expectRecord(item, label));
}

function expectString(record: JsonRecord, key: string): string {
  const value = record[key];
  if (typeof value === "string") return value;
  throw new AgentRunTraceParseError(`Expected string field ${key}`, key);
}

function optionalString(record: JsonRecord, key: string): string | null {
  const value = record[key];
  if (value === null || value === undefined) return null;
  if (typeof value === "string") return value;
  throw new AgentRunTraceParseError(`Expected nullable string field ${key}`, key);
}

function expectBoolean(record: JsonRecord, key: string): boolean {
  const value = record[key];
  if (typeof value === "boolean") return value;
  throw new AgentRunTraceParseError(`Expected boolean field ${key}`, key);
}

function expectNumber(record: JsonRecord, key: string): number {
  const value = record[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  throw new AgentRunTraceParseError(`Expected number field ${key}`, key);
}

function stringArray(record: JsonRecord, key: string): readonly string[] {
  const value = record[key];
  if (!Array.isArray(value)) {
    throw new AgentRunTraceParseError(`Expected string array field ${key}`, key);
  }
  return value.map((item) => {
    if (typeof item === "string") return item;
    throw new AgentRunTraceParseError(`Expected string item in ${key}`, key);
  });
}
