export type AgentRunTraceAssignment = {
  readonly lane: string;
  readonly objective: string;
  readonly field_keys: readonly string[];
  readonly evidence_ids: readonly string[];
  readonly calculation_outputs: readonly string[];
  readonly warnings: readonly string[];
  readonly escalation_required: boolean;
};

export type AgentRunTraceStep = {
  readonly sequence: number;
  readonly kind: string;
  readonly summary: string;
  readonly lane: string | null;
  readonly field_keys: readonly string[];
  readonly evidence_ids: readonly string[];
  readonly calculation_outputs: readonly string[];
  readonly warnings: readonly string[];
  readonly escalation_required: boolean;
};

export type AgentRunTraceArtifact = {
  readonly status: string;
  readonly report_id: string | null;
  readonly document_id: string | null;
  readonly evidence_ids: readonly string[];
  readonly sections: readonly AgentRunTraceReportSection[];
  readonly opportunities: readonly AgentRunTraceOpportunity[];
  readonly assumptions: readonly AgentRunTraceAssumption[];
  readonly message: string | null;
};

export type AgentRunTraceOpportunity = {
  readonly key: string;
  readonly status: "hypothesis";
  readonly current_verified_condition: string;
  readonly proposed_scenario: string;
  readonly required_zoning_entitlement_path: string;
  readonly calculation_outputs: readonly string[];
  readonly upside_mechanism: string;
  readonly blocking_constraints: readonly string[];
  readonly evidence_ids: readonly string[];
  readonly assumptions: readonly string[];
  readonly confidence: number;
  readonly next_verification_step: string;
};

export type AgentRunTraceReportClaim = {
  readonly key: string;
  readonly text: string;
  readonly material: boolean;
  readonly evidence_ids: readonly string[];
};

export type AgentRunTraceReportSection = {
  readonly id: string;
  readonly title: string;
  readonly claims: readonly AgentRunTraceReportClaim[];
  readonly evidence_ids: readonly string[];
};

export type AgentRunTraceAssumptionSource =
  | "agent_run.open_question"
  | "agent_run.escalation"
  | "agent_run.warning";

export type AgentRunTraceAssumptionStatus = "requires_human_review" | "warning";

export type AgentRunTraceAssumption = {
  readonly key: string;
  readonly text: string;
  readonly status: AgentRunTraceAssumptionStatus;
  readonly source: AgentRunTraceAssumptionSource;
  readonly field_key: string | null;
};

export type AgentRunTraceEval = {
  readonly eval_run_id: string;
  readonly eval_case_result_id: string;
  readonly gold_set_case_id: string;
  readonly status: string;
  readonly metric_keys: readonly string[];
  readonly evidence_metric_keys: readonly string[];
  readonly trajectory_metric_keys: readonly string[];
};

export type AgentRunTraceImprovement = {
  readonly baseline_status: "available" | "missing";
  readonly improvement_status: "improved" | "regressed" | "flat" | "no_baseline";
  readonly release_blocked: boolean;
  readonly improved_metric_keys: readonly string[];
  readonly regressed_metric_keys: readonly string[];
  readonly improvement_log: readonly AgentRunTraceImprovementLog[];
};

export type AgentRunTraceImprovementLog = {
  readonly source: string;
  readonly researched_input: string;
  readonly changed_rule: string;
  readonly metric: string;
  readonly direction: string;
  readonly reason: string;
  readonly affected_golden_cases: readonly string[];
  readonly before_score: number;
  readonly after_score: number;
  readonly delta: number;
  readonly gate_blocking: boolean;
  readonly unresolved_risk: string | null;
};

export type AgentRunTraceEvidencePacket = {
  readonly evidence_id: string;
  readonly source_type: string;
  readonly source_authority: string;
  readonly source_title: string;
  readonly source_url: string;
  readonly retrieved_at: string;
  readonly effective_date: string;
  readonly parser_version: string;
  readonly schema_version: string;
  readonly raw_artifact_ref: string;
  readonly referenced_field_keys: readonly string[];
  readonly calculation_outputs: readonly string[];
  readonly lineage: readonly string[];
  readonly confidence: number;
  readonly quality_score: number;
  readonly quality_flags: readonly string[];
  readonly warnings: readonly string[];
};

export type AgentRunTraceSourceRetrieval = {
  readonly evidence_id: string;
  readonly source_type: string;
  readonly source_authority: string;
  readonly publisher: string;
  readonly source_title: string;
  readonly source_url: string;
  readonly retrieved_at: string;
  readonly effective_date: string;
  readonly parser_version: string;
  readonly schema_version: string;
  readonly raw_artifact_ref: string;
  readonly query_parameters: readonly string[];
  readonly referenced_field_keys: readonly string[];
  readonly calculation_outputs: readonly string[];
  readonly lineage: readonly string[];
  readonly quality_score: number;
  readonly quality_flags: readonly string[];
  readonly warnings: readonly string[];
};

export type AgentRunTraceData = {
  readonly run_id: string;
  readonly lookup_snapshot_id: string;
  readonly workspace_id: string;
  readonly project_id: string | null;
  readonly site_id: string | null;
  readonly objective: string;
  readonly status: string;
  readonly ready_for_synthesis: boolean;
  readonly evidence_ids: readonly string[];
  readonly evidence_packets: readonly AgentRunTraceEvidencePacket[];
  readonly source_retrievals: readonly AgentRunTraceSourceRetrieval[];
  readonly warnings: readonly string[];
  readonly open_questions: readonly string[];
  readonly assignments: readonly AgentRunTraceAssignment[];
  readonly escalations: readonly unknown[];
  readonly trace_steps: readonly AgentRunTraceStep[];
  readonly artifact: AgentRunTraceArtifact;
  readonly latest_eval: AgentRunTraceEval | null;
  readonly improvement: AgentRunTraceImprovement | null;
  readonly replay_ready: boolean;
  readonly missing_replay_requirements: readonly string[];
};
