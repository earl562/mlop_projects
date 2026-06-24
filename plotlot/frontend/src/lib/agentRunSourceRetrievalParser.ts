import type { AgentRunTraceSourceRetrieval } from "./agentRunTraceTypes";

type JsonRecord = Record<string, unknown>;

class AgentRunSourceRetrievalParseError extends Error {
  readonly field: string | null;

  constructor(message: string, field: string | null = null) {
    super(message);
    this.name = "AgentRunSourceRetrievalParseError";
    this.field = field;
  }
}

export function parseAgentRunSourceRetrieval(value: JsonRecord): AgentRunTraceSourceRetrieval {
  return {
    evidence_id: expectString(value, "evidence_id"),
    source_type: expectString(value, "source_type"),
    source_authority: expectString(value, "source_authority"),
    publisher: expectString(value, "publisher"),
    source_title: expectString(value, "source_title"),
    source_url: expectString(value, "source_url"),
    retrieved_at: expectString(value, "retrieved_at"),
    effective_date: expectString(value, "effective_date"),
    parser_version: expectString(value, "parser_version"),
    schema_version: expectString(value, "schema_version"),
    raw_artifact_ref: expectString(value, "raw_artifact_ref"),
    query_parameters: stringArray(value, "query_parameters"),
    referenced_field_keys: stringArray(value, "referenced_field_keys"),
    calculation_outputs: stringArray(value, "calculation_outputs"),
    lineage: stringArray(value, "lineage"),
    quality_score: expectNumber(value, "quality_score"),
    quality_flags: stringArray(value, "quality_flags"),
    warnings: stringArray(value, "warnings"),
  };
}

function expectString(record: JsonRecord, key: string): string {
  const value = record[key];
  if (typeof value === "string") return value;
  throw new AgentRunSourceRetrievalParseError(`Expected string field ${key}`, key);
}

function expectNumber(record: JsonRecord, key: string): number {
  const value = record[key];
  if (typeof value === "number" && Number.isFinite(value)) return value;
  throw new AgentRunSourceRetrievalParseError(`Expected number field ${key}`, key);
}

function stringArray(record: JsonRecord, key: string): readonly string[] {
  const value = record[key];
  if (!Array.isArray(value)) {
    throw new AgentRunSourceRetrievalParseError(`Expected string array field ${key}`, key);
  }
  return value.map((item) => {
    if (typeof item === "string") return item;
    throw new AgentRunSourceRetrievalParseError(`Expected string item in ${key}`, key);
  });
}
