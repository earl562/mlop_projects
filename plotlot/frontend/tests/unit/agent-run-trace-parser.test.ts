import { describe, expect, it } from "vitest";
import { parseAgentRunTrace } from "../../src/lib/agentRunTraceParser";
import { agentRunTrace } from "../fixtures/agentRunTrace";

describe("parseAgentRunTrace", () => {
  it("preserves artifact assumptions separately from evidence IDs", () => {
    const trace = parseAgentRunTrace(agentRunTrace);
    const [assumption] = trace.artifact.assumptions;
    const [section] = trace.artifact.sections;
    const [opportunity] = trace.artifact.opportunities;

    expect(trace.artifact.evidence_ids).toEqual(["evidence-parcel-e2e", "evidence-zoning-e2e"]);
    expect(section).toEqual({
      id: "evidence_scope",
      title: "Evidence Scope",
      evidence_ids: ["evidence-parcel-e2e", "evidence-zoning-e2e"],
      claims: [
        {
          key: "evidence.scope",
          text: "The run summary is limited to recorded lookup evidence.",
          material: true,
          evidence_ids: ["evidence-parcel-e2e", "evidence-zoning-e2e"],
        },
      ],
    });
    expect(trace.source_retrievals).toHaveLength(2);
    expect(trace.source_retrievals).toContainEqual(
      {
        evidence_id: "evidence-parcel-e2e",
        source_type: "parcel_appraiser",
        source_authority: "authoritative_public_record",
        publisher: "Broward County Property Appraiser",
        source_title: "Recorded parcel appraiser packet",
        source_url: "https://bcpa.net/parcel/504210230010",
        retrieved_at: "2026-06-22T00:00:00Z",
        effective_date: "2026-01-01",
        parser_version: "parcel-parser@1",
        schema_version: "parcel-v1",
        raw_artifact_ref: "raw://parcel/evidence-parcel-e2e",
        query_parameters: ["folio=504210230010"],
        referenced_field_keys: ["parcel.apn"],
        calculation_outputs: [],
        lineage: ["source", "raw_artifact", "normalized_evidence", "displayed_field"],
        quality_score: 0.98,
        quality_flags: [],
        warnings: [],
      },
    );
    expect(assumption).toEqual({
      key: "open_question.1",
      text: "standards.setbacks.front is unknown; retrieve authoritative evidence before use.",
      status: "requires_human_review",
      source: "agent_run.open_question",
      field_key: null,
    });
    expect(opportunity).toEqual({
      key: "opportunity.by_right_capacity",
      status: "hypothesis",
      current_verified_condition: "Recorded lookup evidence supports max_units=1.",
      proposed_scenario: "Test by-right development capacity using recorded zoning evidence.",
      required_zoning_entitlement_path:
        "By-right scenario only; entitlement upside remains unverified until official local evidence is retrieved.",
      calculation_outputs: ["max_units=1"],
      upside_mechanism:
        "Developer value may exist if the by-right unit yield exceeds the current use.",
      blocking_constraints: [
        "Market rents, costs, financing terms, and entitlement outcomes are not verified by the lookup snapshot.",
      ],
      evidence_ids: ["evidence-zoning-e2e"],
      assumptions: [
        "Market rents, costs, financing terms, exit values, and lender terms remain underwriting assumptions until sourced.",
      ],
      confidence: 0.6,
      next_verification_step:
        "Confirm market rents, costs, financing terms, and any missing dimensional standards before underwriting value.",
    });
    expect(trace.improvement?.improvement_log[0]).toEqual({
      source: "agent_run_eval",
      researched_input: "run_e2e_agent",
      changed_rule: "eval_metric:evidence_coverage",
      metric: "evidence_coverage",
      direction: "improved",
      reason: "baseline_delta",
      affected_golden_cases: ["gold_e2e_agent"],
      before_score: 0.9,
      after_score: 1,
      delta: 0.1,
      gate_blocking: false,
      unresolved_risk: null,
    });
  });

  it("rejects malformed trust-critical trace arrays", () => {
    expect(() =>
      parseAgentRunTrace({
        ...agentRunTrace,
        evidence_ids: "evidence-parcel-e2e",
      }),
    ).toThrow("Expected string array field evidence_ids");

    expect(() =>
      parseAgentRunTrace({
        ...agentRunTrace,
        evidence_packets: [{ ...agentRunTrace.evidence_packets[0], lineage: [42] }],
      }),
    ).toThrow("Expected string item in lineage");

    expect(() =>
      parseAgentRunTrace({
        ...agentRunTrace,
        source_retrievals: [{ ...agentRunTrace.source_retrievals[0], query_parameters: [42] }],
      }),
    ).toThrow("Expected string item in query_parameters");

    expect(() =>
      parseAgentRunTrace({
        ...agentRunTrace,
        artifact: {
          ...agentRunTrace.artifact,
          sections: [{ ...agentRunTrace.artifact.sections[0], evidence_ids: [42] }],
        },
      }),
    ).toThrow("Expected string item in evidence_ids");

    expect(() =>
      parseAgentRunTrace({
        ...agentRunTrace,
        artifact: {
          ...agentRunTrace.artifact,
          opportunities: [{ ...agentRunTrace.artifact.opportunities[0], status: "verified" }],
        },
      }),
    ).toThrow("Invalid agent run opportunity status");
  });

  it("rejects unsupported artifact assumption sources", () => {
    expect(() =>
      parseAgentRunTrace({
        ...agentRunTrace,
        artifact: {
          ...agentRunTrace.artifact,
          assumptions: [
            {
              ...agentRunTrace.artifact.assumptions[0],
              source: "untrusted.summary",
            },
          ],
        },
      }),
    ).toThrow("Invalid agent run assumption source");
  });
});
