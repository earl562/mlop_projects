import type {
  AgentRunTraceReportClaim,
  AgentRunTraceReportSection,
} from "./agentRunTraceTypes";

type JsonRecord = Record<string, unknown>;

class AgentRunReportSectionParseError extends Error {
  readonly field: string | null;

  constructor(message: string, field: string | null = null) {
    super(message);
    this.name = "AgentRunReportSectionParseError";
    this.field = field;
  }
}

export function parseAgentRunReportSections(
  value: unknown,
): readonly AgentRunTraceReportSection[] {
  return recordArray(value, "agent run artifact report sections").map(parseReportSection);
}

function parseReportSection(value: JsonRecord): AgentRunTraceReportSection {
  return {
    id: expectString(value, "id"),
    title: expectString(value, "title"),
    claims: recordArray(value.claims, "agent run artifact report claims").map(parseReportClaim),
    evidence_ids: stringArray(value, "evidence_ids"),
  };
}

function parseReportClaim(value: JsonRecord): AgentRunTraceReportClaim {
  return {
    key: expectString(value, "key"),
    text: expectString(value, "text"),
    material: expectBoolean(value, "material"),
    evidence_ids: stringArray(value, "evidence_ids"),
  };
}

function recordArray(value: unknown, label: string): readonly JsonRecord[] {
  if (!Array.isArray(value)) throw new AgentRunReportSectionParseError(`Invalid ${label} payload`);
  return value.map((item) => expectRecord(item, label));
}

function expectRecord(value: unknown, label: string): JsonRecord {
  if (typeof value === "object" && value !== null && !Array.isArray(value)) {
    return Object.fromEntries(Object.entries(value));
  }
  throw new AgentRunReportSectionParseError(`Invalid ${label} payload`);
}

function expectString(record: JsonRecord, key: string): string {
  const value = record[key];
  if (typeof value === "string") return value;
  throw new AgentRunReportSectionParseError(`Expected string field ${key}`, key);
}

function expectBoolean(record: JsonRecord, key: string): boolean {
  const value = record[key];
  if (typeof value === "boolean") return value;
  throw new AgentRunReportSectionParseError(`Expected boolean field ${key}`, key);
}

function stringArray(record: JsonRecord, key: string): readonly string[] {
  const value = record[key];
  if (!Array.isArray(value)) {
    throw new AgentRunReportSectionParseError(`Expected string array field ${key}`, key);
  }
  return value.map((item) => {
    if (typeof item === "string") return item;
    throw new AgentRunReportSectionParseError(`Expected string item in ${key}`, key);
  });
}
