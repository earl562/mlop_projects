"use client";

import { AlertTriangle, CheckCircle2 } from "lucide-react";

import type { AgentRunImprovementSummary } from "@/lib/agentRuns";

export default function AgentRunReleaseGateSummary({
  summary,
}: {
  readonly summary: AgentRunImprovementSummary | null;
}) {
  if (summary === null) return null;

  return (
    <div
      className={summary.release_blocked ? blockedClass : clearClass}
      data-testid="agent-run-release-gate"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          {summary.release_blocked ? (
            <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
          ) : (
            <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" />
          )}
          <div className="min-w-0">
            <div className="text-xs font-semibold text-[var(--text-primary)]">
              {summary.release_blocked ? "Release blocked" : "Release gate clear"}
            </div>
            <div className="mt-0.5 text-[11px] text-[var(--text-secondary)]">
              Baseline {summary.baseline_status}; trend {summary.improvement_status}
            </div>
          </div>
        </div>
        <span className="rounded-full border border-[var(--border-soft)] px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
          {summary.current.status}
        </span>
      </div>

      <MetricKeyList
        label="Regressed"
        metricKeys={summary.regressed_metric_keys}
        tone="danger"
      />
      <MetricKeyList
        label="Improved"
        metricKeys={summary.improved_metric_keys}
        tone="success"
      />
    </div>
  );
}

function MetricKeyList({
  label,
  metricKeys,
  tone,
}: {
  readonly label: string;
  readonly metricKeys: readonly string[];
  readonly tone: "danger" | "success";
}) {
  if (metricKeys.length === 0) return null;
  const toneClass = tone === "danger" ? "text-[var(--danger)]" : "text-[var(--success)]";
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
      <span className={`font-semibold ${toneClass}`}>{label}</span>
      {metricKeys.map((metricKey) => (
        <span
          className="rounded border border-[var(--border-soft)] bg-[var(--bg-surface)] px-2 py-1 font-mono text-[10px] font-semibold text-[var(--text-primary)]"
          key={metricKey}
        >
          {metricKey}
        </span>
      ))}
    </div>
  );
}

const clearClass =
  "mt-4 rounded-lg border border-[var(--success)] bg-[var(--success-subtle)] px-3 py-2 text-xs";

const blockedClass =
  "mt-4 rounded-lg border border-[var(--danger)] bg-[var(--danger-subtle)] px-3 py-2 text-xs";
