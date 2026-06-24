"use client";

import { Play, RefreshCw } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import {
  fetchLookupReleaseGate,
  runLookupGoldenEvalBatch,
  type LookupReleaseGateData,
} from "@/lib/lookupReleaseGate";
import {
  BlockerList,
  EmptyRunState,
  FailureList,
  ImprovementLog,
  MetricCard,
  RunMeta,
  decisionIcon,
  decisionPillClass,
  loadingLabels,
  summaryText,
  topMetricCards,
  type LookupReleaseGateLoadState,
} from "./LookupReleaseGatePanelParts";

type GoldenEvalRunState = "idle" | "running" | "complete" | "error";

type LookupReleaseGatePanelProps = {
  readonly suite?: string;
  readonly snapshotId?: string | null;
  readonly address?: string | null;
};

export default function LookupReleaseGatePanel({
  suite = "lookup_correctness",
  snapshotId = null,
  address = null,
}: LookupReleaseGatePanelProps) {
  const [loadState, setLoadState] = useState<LookupReleaseGateLoadState>("loading");
  const [gate, setGate] = useState<LookupReleaseGateData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [runState, setRunState] = useState<GoldenEvalRunState>("idle");
  const [runMessage, setRunMessage] = useState<string | null>(null);
  const panelRef = useRef<HTMLElement | null>(null);
  const latestRun = gate?.latest_run ?? null;
  const metricCards = useMemo(() => topMetricCards(latestRun), [latestRun]);
  const canRunGoldenEval = Boolean(snapshotId && address) && runState !== "running";

  const loadGate = async () => {
    setLoadState("loading");
    setError(null);
    try {
      const nextGate = await fetchLookupReleaseGate(suite);
      setGate(nextGate);
      setLoadState("ready");
    } catch (caught) {
      setGate(null);
      setError(caught instanceof Error ? caught.message : "Lookup release gate failed");
      setLoadState("error");
    }
  };

  const runGoldenEval = async () => {
    if (!snapshotId || !address || runState === "running") return;
    setRunState("running");
    setRunMessage(null);
    try {
      const result = await runLookupGoldenEvalBatch({
        suite,
        snapshots: [{ snapshot_id: snapshotId, address }],
        use_latest_baseline: true,
      });
      await loadGate();
      setRunState("complete");
      setRunMessage(`Recorded ${result.case_results.length} golden case eval.`);
      requestAnimationFrame(() => {
        panelRef.current?.scrollIntoView?.({ behavior: "smooth", block: "center" });
      });
    } catch (caught) {
      setRunState("error");
      setRunMessage(caught instanceof Error ? caught.message : "Lookup golden eval failed");
    }
  };

  useEffect(() => {
    let active = true;
    setLoadState("loading");
    setError(null);
    fetchLookupReleaseGate(suite)
      .then((nextGate) => {
        if (!active) return;
        setGate(nextGate);
        setLoadState("ready");
      })
      .catch((caught) => {
        if (!active) return;
        setGate(null);
        setError(caught instanceof Error ? caught.message : "Lookup release gate failed");
        setLoadState("error");
      });
    return () => {
      active = false;
    };
  }, [suite]);

  const releaseBlocked = gate?.release_blocked ?? true;
  const statusLabel = loadState === "loading" ? "Checking" : releaseBlocked ? "Blocked" : "Passed";

  return (
    <section
      ref={panelRef}
      className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface-raised)] p-4 shadow-[var(--shadow-card)]"
      data-testid="lookup-release-gate-panel"
      aria-label="Lookup correctness release gate"
    >
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className={decisionPillClass(loadState, releaseBlocked)} data-testid="lookup-release-gate-decision">
              {decisionIcon(loadState, releaseBlocked)}
              {statusLabel}
            </span>
            <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
              {suite}
            </span>
          </div>
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">
            Lookup correctness gate
          </h2>
          <p className="mt-1 max-w-2xl text-xs leading-5 text-[var(--text-secondary)]">
            {summaryText(loadState, gate, error)}
          </p>
        </div>
        <div className="flex flex-wrap gap-2 md:justify-end">
          {snapshotId && address && (
            <button
              type="button"
              onClick={() => {
                void runGoldenEval();
              }}
              disabled={!canRunGoldenEval}
              className="inline-flex min-h-[40px] shrink-0 items-center justify-center gap-2 rounded-lg bg-[var(--text-primary)] px-3 py-2 text-xs font-semibold text-[var(--bg-primary)] transition-all hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand)] active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-35"
              data-testid="lookup-release-gate-run"
            >
              <Play className="h-3.5 w-3.5" aria-hidden="true" />
              {runState === "running" ? "Running eval" : "Run golden eval"}
            </button>
          )}
          <button
            type="button"
            onClick={() => {
              void loadGate();
            }}
            className="inline-flex min-h-[40px] shrink-0 items-center justify-center gap-2 rounded-lg border border-[var(--border)] bg-[var(--bg-surface)] px-3 py-2 text-xs font-semibold text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-surface-raised)] hover:text-[var(--text-primary)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand)]"
            data-testid="lookup-release-gate-refresh"
          >
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            Refresh
          </button>
        </div>
      </div>

      {runState === "error" && runMessage && (
        <div
          className="mt-3 rounded-lg border border-[var(--danger)] bg-[var(--danger-subtle)] px-3 py-2 text-xs text-[var(--danger)]"
          data-testid="lookup-release-gate-run-error"
        >
          {runMessage}
        </div>
      )}

      {runState === "complete" && runMessage && (
        <div
          className="mt-3 rounded-lg border border-[var(--success)] bg-[var(--success-subtle)] px-3 py-2 text-xs text-[var(--success)]"
          data-testid="lookup-release-gate-run-success"
        >
          {runMessage}
        </div>
      )}

      {loadState === "loading" && (
        <div className="mt-4 grid grid-cols-2 gap-2 md:grid-cols-4" data-testid="lookup-release-gate-loading">
          {loadingLabels.map((label) => (
            <MetricCard key={label} label={label} value="..." />
          ))}
        </div>
      )}

      {loadState === "ready" && gate && (
        <div className="mt-4 space-y-4">
          {latestRun ? (
            <>
              <div className="grid grid-cols-2 gap-2 md:grid-cols-4">
                {metricCards.map((metric) => (
                  <MetricCard key={metric.label} label={metric.label} value={metric.value} />
                ))}
              </div>
              <RunMeta run={latestRun} />
              <BlockerList blockers={gate.blockers} />
              <FailureList failures={latestRun.gate_failures} />
              <ImprovementLog entries={latestRun.improvement_log} />
            </>
          ) : (
            <>
              <EmptyRunState reason={gate.reason} />
              <BlockerList blockers={gate.blockers} />
            </>
          )}
        </div>
      )}

      {loadState === "error" && (
        <div
          className="mt-4 rounded-lg border border-[var(--danger)] bg-[var(--danger-subtle)] px-3 py-2 text-xs text-[var(--danger)]"
          data-testid="lookup-release-gate-error"
        >
          {error ?? "Lookup release gate failed"}
        </div>
      )}
    </section>
  );
}
