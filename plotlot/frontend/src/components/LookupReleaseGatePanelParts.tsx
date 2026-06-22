import { AlertTriangle, CheckCircle2, ShieldAlert } from "lucide-react";

import type {
  LookupReleaseGateBlocker,
  LookupReleaseGateData,
  LookupReleaseGateFailure,
  LookupReleaseGateImprovementEntry,
  LookupReleaseGateRun,
} from "@/lib/lookupReleaseGate";

export type LookupReleaseGateLoadState = "loading" | "ready" | "error";

export function RunMeta({ run }: { readonly run: LookupReleaseGateRun }) {
  return (
    <div className="grid grid-cols-1 gap-2 border-t border-[var(--border-soft)] pt-3 text-xs sm:grid-cols-3">
      <MetaValue label="Eval run" value={run.eval_run_id} />
      <MetaValue label="Cases" value={run.case_ids.length.toString()} />
      <MetaValue label="Snapshots" value={run.lookup_snapshot_ids.length.toString()} />
    </div>
  );
}

export function EmptyRunState({ reason }: { readonly reason: string }) {
  return (
    <div
      className="rounded-lg border border-[var(--warning)] bg-[var(--warning-subtle)] px-3 py-2 text-xs text-[var(--warning)]"
      data-testid="lookup-release-gate-empty"
    >
      No completed lookup-correctness eval run is available. Reason: {reason}.
    </div>
  );
}

export function BlockerList({
  blockers,
}: {
  readonly blockers: readonly LookupReleaseGateBlocker[];
}) {
  if (blockers.length === 0) return null;
  return (
    <div className="space-y-2" data-testid="lookup-release-gate-blockers">
      <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--danger)]">
        Blockers
      </div>
      {blockers.map((blocker) => (
        <div
          className="rounded-lg border border-[var(--danger)] bg-[var(--danger-subtle)] px-3 py-2 text-xs text-[var(--danger)]"
          key={`${blocker.code}-${blocker.metric ?? blocker.status ?? blocker.message}`}
        >
          <div className="font-semibold text-[var(--text-primary)]">{blocker.code}</div>
          <div className="mt-1 leading-5">{blocker.message}</div>
          {blocker.metric && (
            <div className="mt-1 font-mono text-[10px]">
              {blocker.metric}
              {blocker.current !== null && blocker.baseline !== null
                ? ` current ${formatMetricValue(blocker.metric, blocker.current)} / baseline ${formatMetricValue(blocker.metric, blocker.baseline)}`
                : ""}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

export function FailureList({
  failures,
}: {
  readonly failures: readonly LookupReleaseGateFailure[];
}) {
  if (failures.length === 0) return null;
  return (
    <div className="space-y-2" data-testid="lookup-release-gate-failures">
      <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
        Gate failures
      </div>
      {failures.map((failure) => (
        <div
          className="rounded-lg border border-[var(--border-soft)] bg-[var(--bg-surface)] px-3 py-2 text-xs text-[var(--text-secondary)]"
          key={`${failure.metric}-${failure.reason ?? "unknown"}`}
        >
          <span className="font-mono text-[var(--text-primary)]">{failure.metric}</span>
          {failure.reason && <span> {failure.reason}</span>}
        </div>
      ))}
    </div>
  );
}

export function ImprovementLog({
  entries,
}: {
  readonly entries: readonly LookupReleaseGateImprovementEntry[];
}) {
  if (entries.length === 0) return null;
  return (
    <div className="space-y-2" data-testid="lookup-release-gate-improvement-log">
      <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
        Improvement log
      </div>
      {entries.slice(0, 3).map((entry) => (
        <div
          className="rounded-lg border border-[var(--border-soft)] bg-[var(--bg-surface)] px-3 py-2 text-xs"
          key={`${entry.changed_rule}-${entry.metric ?? "metric"}`}
        >
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-[10px] font-semibold text-[var(--text-primary)]">
              {entry.changed_rule}
            </span>
            {entry.direction && (
              <span
                className={
                  entry.direction === "regressed"
                    ? "text-[var(--danger)]"
                    : "text-[var(--success)]"
                }
              >
                {entry.direction}
              </span>
            )}
            {entry.delta !== null && (
              <span className="font-mono text-[10px] text-[var(--text-muted)]">
                {formatSigned(entry.delta)}
              </span>
            )}
          </div>
          {entry.unresolved_risk && (
            <div className="mt-1 leading-5 text-[var(--text-secondary)]">
              {entry.unresolved_risk}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

export function MetricCard({ label, value }: { readonly label: string; readonly value: string }) {
  return (
    <div className="min-h-[58px] rounded-lg bg-[var(--bg-surface)] px-3 py-2">
      <div className="truncate text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
        {label}
      </div>
      <div className="mt-1 font-mono text-sm font-semibold text-[var(--text-primary)]">
        {value}
      </div>
    </div>
  );
}

export function summaryText(
  loadState: LookupReleaseGateLoadState,
  gate: LookupReleaseGateData | null,
  error: string | null,
): string {
  if (loadState === "loading") return "Checking the latest recorded lookup-correctness batch eval.";
  if (loadState === "error") return error ?? "Lookup release gate failed.";
  if (!gate) return "Lookup release gate unavailable.";
  if (gate.latest_run === null) return "Release is blocked until a completed batch eval is recorded.";
  if (gate.release_blocked) return `Release blocked: ${gate.reason}.`;
  return `Latest eval passed: ${gate.latest_run.eval_run_id}.`;
}

export function topMetricCards(
  run: LookupReleaseGateRun | null,
): readonly { readonly label: string; readonly value: string }[] {
  if (!run) return [];
  const preferredKeys = [
    "pass_rate",
    "citation_coverage",
    "unsupported_claim_rate",
    "deterministic_calculation_reproducibility",
  ];
  const cards = preferredKeys
    .filter((key) => key in run.metrics)
    .map((key) => ({
      label: metricDisplayLabel(key),
      value: formatMetricValue(key, run.metrics[key] ?? 0),
    }));
  if (cards.length > 0) return cards;
  return Object.entries(run.metrics)
    .slice(0, 4)
    .map(([key, value]) => ({
      label: metricDisplayLabel(key),
      value: formatMetricValue(key, value),
    }));
}

export function decisionPillClass(
  loadState: LookupReleaseGateLoadState,
  releaseBlocked: boolean,
): string {
  const base = "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold";
  if (loadState === "loading") {
    return `${base} border-[var(--brand-soft-border)] bg-[var(--brand-subtle)] text-[var(--brand)]`;
  }
  if (releaseBlocked) {
    return `${base} border-[var(--danger)] bg-[var(--danger-subtle)] text-[var(--danger)]`;
  }
  return `${base} border-[var(--success)] bg-[var(--success-subtle)] text-[var(--success)]`;
}

export function decisionIcon(
  loadState: LookupReleaseGateLoadState,
  releaseBlocked: boolean,
) {
  if (loadState === "loading") return <ShieldAlert className="h-3.5 w-3.5" aria-hidden="true" />;
  if (releaseBlocked) return <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />;
  return <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />;
}

function MetaValue({ label, value }: { readonly label: string; readonly value: string }) {
  return (
    <div className="min-w-0">
      <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
        {label}
      </div>
      <div className="mt-1 truncate font-mono text-xs font-semibold text-[var(--text-primary)]">
        {value}
      </div>
    </div>
  );
}

function formatMetricValue(metric: string, value: number): string {
  if (metric === "case_count" || metric === "passed_count" || metric === "failed_count") {
    return Math.round(value).toString();
  }
  return `${Math.round(value * 100)}%`;
}

function formatSigned(value: number): string {
  const sign = value > 0 ? "+" : "";
  return `${sign}${Math.round(value * 100)}%`;
}

function metricDisplayLabel(metric: string): string {
  const labels: Readonly<Record<string, string>> = {
    pass_rate: "Pass rate",
    citation_coverage: "Citation",
    unsupported_claim_rate: "Unsupported",
    deterministic_calculation_reproducibility: "Calc replay",
  };
  return labels[metric] ?? metric;
}

export const loadingLabels = ["Pass rate", "Citation", "Unsupported", "Calc replay"];
