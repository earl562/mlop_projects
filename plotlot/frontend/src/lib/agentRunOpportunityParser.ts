import type { AgentRunTraceOpportunity } from "./agentRunTraceTypes";

type JsonRecord = Record<string, unknown>;

class AgentRunOpportunityParseError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AgentRunOpportunityParseError";
  }
}

export function parseAgentRunOpportunity(value: JsonRecord): AgentRunTraceOpportunity {
  return {
    key: expectString(value, "key"),
    status: parseOpportunityStatus(value.status),
    current_verified_condition: expectString(value, "current_verified_condition"),
    proposed_scenario: expectString(value, "proposed_scenario"),
    required_zoning_entitlement_path: expectString(value, "required_zoning_entitlement_path"),
    calculation_outputs: stringArray(value, "calculation_outputs"),
    upside_mechanism: expectString(value, "upside_mechanism"),
    blocking_constraints: stringArray(value, "blocking_constraints"),
    evidence_ids: stringArray(value, "evidence_ids"),
    assumptions: stringArray(value, "assumptions"),
    confidence: expectNumber(value, "confidence"),
    next_verification_step: expectString(value, "next_verification_step"),
  };
}

function parseOpportunityStatus(value: unknown): "hypothesis" {
  if (value === "hypothesis") return value;
  throw new AgentRunOpportunityParseError("Invalid agent run opportunity status");
}

function expectString(record: JsonRecord, key: string): string {
  const value = record[key];
  if (typeof value === "string") return value;
  throw new AgentRunOpportunityParseError(`Expected string field ${key}`);
}

function expectNumber(record: JsonRecord, key: string): number {
  const value = record[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  throw new AgentRunOpportunityParseError(`Expected number field ${key}`);
}

function stringArray(record: JsonRecord, key: string): readonly string[] {
  const value = record[key];
  if (!Array.isArray(value)) {
    throw new AgentRunOpportunityParseError(`Expected string array field ${key}`);
  }
  return value.map((item) => {
    if (typeof item === "string") return item;
    throw new AgentRunOpportunityParseError(`Expected string item in ${key}`);
  });
}
