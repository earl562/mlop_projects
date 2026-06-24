"use client";

import { AlertTriangle, CheckCircle2, Play, ShieldCheck, XCircle } from "lucide-react";
import { useMemo, useRef, useState } from "react";

import {
  DEFAULT_AGENT_RUN_WORKSPACE_ID,
  evaluateAgentRun,
  fetchAgentRunImprovementSummary,
  startAgentRun,
  type AgentRunEvalRecord,
  type AgentRunImprovementSummary,
} from "@/lib/agentRuns";
import { fetchAgentRunTrace, type AgentRunTraceData } from "@/lib/agentRunTrace";
import type { ZoningReportData } from "@/lib/api";
import AgentRunReleaseGateSummary from "./AgentRunReleaseGateSummary";
import AgentRunSnapshotEvidence from "./AgentRunSnapshotEvidence";
import AgentRunTraceSummary from "./AgentRunTraceSummary";

type RunState = "idle" | "starting" | "evaluating" | "ready" | "error";

type SnapshotStats = {
  readonly fieldCount: number;
  readonly evidenceCount: number;
  readonly warningCount: number;
};

const stateLabel: Readonly<Record<RunState, string>> = {
  idle: "Ready",
  starting: "Starting run",
  evaluating: "Scoring eval",
  ready: "Complete",
  error: "Needs attention",
};

export default function AgentRunPanel({ report }: { readonly report: ZoningReportData }) {
  const snapshot = report.lookup_snapshot ?? null;
  const [runState, setRunState] = useState<RunState>("idle");
  const [evalRecord, setEvalRecord] = useState<AgentRunEvalRecord | null>(null);
  const [summary, setSummary] = useState<AgentRunImprovementSummary | null>(null);
  const [trace, setTrace] = useState<AgentRunTraceData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const panelRef = useRef<HTMLElement | null>(null);
  const stats = useMemo(() => snapshotStats(snapshot), [snapshot]);
  const blocked = summary?.release_blocked ?? false;
  const isRunning = runState === "starting" || runState === "evaluating";
  const canRun = snapshot !== null && !isRunning;

  const handleRun = async () => {
    if (!snapshot || isRunning) return;
    setRunState("starting");
    setEvalRecord(null);
    setSummary(null);
    setTrace(null);
    setError(null);
    try {
      const run = await startAgentRun({
        lookupSnapshotId: snapshot.lookup_snapshot_id,
        objective: "Evaluate this lookup snapshot for agentic developer-value discovery.",
        workspaceId: DEFAULT_AGENT_RUN_WORKSPACE_ID,
      });
      setRunState("evaluating");
      const nextEval = await evaluateAgentRun(run.run_id, run.workspace_id);
      const [nextSummary, nextTrace] = await Promise.all([
        fetchAgentRunImprovementSummary(run.run_id, run.workspace_id),
        fetchAgentRunTrace(run.run_id, run.workspace_id),
      ]);
      setEvalRecord(nextEval);
      setSummary(nextSummary);
      setTrace(nextTrace);
      setRunState("ready");
      requestAnimationFrame(() => {
        panelRef.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Agent harness run failed");
      setRunState("error");
    }
  };

  return (
    <section
      ref={panelRef}
      className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface-raised)] p-4"
      data-testid="agent-run-panel"
      aria-label="Agent harness gate"
    >
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className={statusPillClass(runState, blocked)} data-testid="agent-run-status">
              {statusIcon(runState, blocked)}
              {blocked ? "Blocked" : stateLabel[runState]}
            </span>
            <span className="text-xs font-medium text-[var(--text-muted)]">
              {snapshot ? `Snapshot ${snapshot.lookup_snapshot_id}` : "No lookup snapshot"}
            </span>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-[var(--text-primary)]">
              Agentic harness eval
            </h3>
            <p className="mt-1 max-w-2xl text-xs leading-5 text-[var(--text-secondary)]">
              {snapshot
                ? "Run the specialist lanes against the recorded evidence, then score citation coverage, trace replayability, and regression risk."
                : "The agent harness is unavailable because this report does not include a recorded lookup snapshot."}
            </p>
          </div>
          <div className="grid grid-cols-3 gap-2 sm:max-w-lg">
            <Metric label="Fields" value={stats.fieldCount.toString()} />
            <Metric label="Evidence IDs" value={stats.evidenceCount.toString()} />
            <Metric label="Warnings" value={stats.warningCount.toString()} />
          </div>
        </div>
        <button
          type="button"
          onClick={handleRun}
          disabled={!canRun}
          className="inline-flex min-h-[44px] shrink-0 items-center justify-center gap-2 rounded-lg bg-[var(--text-primary)] px-4 py-2 text-sm font-semibold text-[var(--bg-primary)] transition-all hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand)] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-35"
          data-testid="agent-run-start"
        >
          <Play className="h-4 w-4" aria-hidden="true" />
          {isRunning ? "Running" : "Run harness eval"}
        </button>
      </div>

      <AgentRunSnapshotEvidence snapshot={snapshot} />

      <AgentRunReleaseGateSummary summary={summary} />

      {evalRecord && (
        <div className="mt-3 grid grid-cols-2 gap-2 border-t border-[var(--border-soft)] pt-3 sm:grid-cols-3 lg:grid-cols-6">
          <Metric label="Evidence" value={formatPercent(evalRecord.metrics.evidence_coverage)} />
          <Metric label="Trace" value={formatPercent(evalRecord.metrics.trace_replayability)} />
          <Metric label="Citations" value={formatPercent(evalRecord.metrics.artifact_citation_coverage)} />
          <Metric
            label="Opportunity"
            value={formatPercent(evalRecord.metrics.opportunity_hypothesis_completeness)}
          />
          <Metric
            label="Assumptions"
            value={formatPercent(evalRecord.metrics.assumption_label_coverage)}
          />
          <Metric label="Unsupported" value={formatPercent(evalRecord.metrics.unsupported_claim_rate)} />
        </div>
      )}

      <AgentRunTraceSummary trace={trace} />

      {error && (
        <div className="mt-3 rounded-lg border border-[var(--danger)] bg-[var(--danger-subtle)] px-3 py-2 text-xs text-[var(--danger)]">
          {error}
        </div>
      )}
    </section>
  );
}

function Metric({ label, value }: { readonly label: string; readonly value: string }) {
  return (
    <div className="min-h-[58px] rounded-lg bg-[var(--bg-surface)] px-3 py-2">
      <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
        {label}
      </div>
      <div className="mt-1 font-mono text-sm font-semibold text-[var(--text-primary)]">
        {value}
      </div>
    </div>
  );
}

function snapshotStats(snapshot: ZoningReportData["lookup_snapshot"]): SnapshotStats {
  if (!snapshot) {
    return { fieldCount: 0, evidenceCount: 0, warningCount: 0 };
  }
  const evidenceIds = new Set<string>();
  for (const field of snapshot.fields) {
    for (const evidenceId of field.evidence_ids) {
      evidenceIds.add(evidenceId);
    }
  }
  for (const calculation of snapshot.calculations) {
    for (const evidenceId of calculation.input_evidence_ids) {
      evidenceIds.add(evidenceId);
    }
  }
  const fieldWarningCount = snapshot.fields.reduce(
    (total, field) => total + field.warnings.length,
    0,
  );
  const calculationWarningCount = snapshot.calculations.reduce(
    (total, calculation) => total + calculation.warnings.length,
    0,
  );
  return {
    fieldCount: snapshot.fields.length,
    evidenceCount: evidenceIds.size,
    warningCount: snapshot.warnings.length + fieldWarningCount + calculationWarningCount,
  };
}

function formatPercent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function statusPillClass(state: RunState, blocked: boolean): string {
  const base =
    "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold";
  if (blocked || state === "error") {
    return `${base} border-[var(--danger)] bg-[var(--danger-subtle)] text-[var(--danger)]`;
  }
  if (state === "ready") {
    return `${base} border-[var(--success)] bg-[var(--success-subtle)] text-[var(--success)]`;
  }
  return `${base} border-[var(--brand-soft-border)] bg-[var(--brand-subtle)] text-[var(--brand)]`;
}

function statusIcon(state: RunState, blocked: boolean) {
  if (blocked) return <XCircle className="h-3.5 w-3.5" aria-hidden="true" />;
  if (state === "ready") return <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />;
  if (state === "error") return <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />;
  return <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" />;
}
