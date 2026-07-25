"use client";

import { useMemo, useState } from "react";

import {
  type HarnessRunResultData,
} from "@/lib/api";
import {
  createAnalysisLifecycleRecord,
  runLifecycleAwareHarnessAnalysis,
} from "@/lib/harness-analysis-lifecycle";
import {
  HarnessLifecycleContextFields,
  type HarnessLifecycleContextValue,
} from "@/components/HarnessLifecycleContextFields";
import { HarnessAnalystRunSummary } from "@/components/HarnessAnalystRunSummary";

type SourceMode = "fixture" | "live";
type AnalysisType = "acquisition_memo" | "zoning_research" | "lender_package";

const DEFAULT_ASSUMPTIONS = {
  avgUnitSizeSf: 850,
  efficiencyFactor: 0.85,
  monthlyRentPerUnit: 2350,
  operatingExpensePct: 0.34,
  capRate: 0.0575,
  maxFar: 2,
  maxUnits: 16,
  desiredProfit: 350000,
  hardCosts: 2600000,
  softCosts: 650000,
  contingency: 220000,
  developerFee: 180000,
  closingCosts: 90000,
  financingCosts: 240000,
  holdingCosts: 120000,
  sellingCosts: 150000,
};

export default function HarnessAnalystWorkbench() {
  const [address, setAddress] = useState("171 NE 209th Ter, Miami, FL 33179");
  const [analysisType, setAnalysisType] = useState<AnalysisType>("acquisition_memo");
  const [sourceMode, setSourceMode] = useState<SourceMode>("live");
  const [lifecycle, setLifecycle] = useState<HarnessLifecycleContextValue>({
    enabled: false,
    workspaceId: "",
    projectId: "",
    siteId: "",
    analysisId: "",
    analysisName: "Shared harness analysis",
  });
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<HarnessRunResultData | null>(null);

  const warnings = useMemo(() => {
    if (!result) return [];
    const raw = result.artifacts?.warnings;
    return Array.isArray(raw) ? raw.filter((item): item is string => typeof item === "string") : [];
  }, [result]);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setRunning(true);
    setError(null);
    try {
      const hasLifecycleContext = lifecycle.enabled;
      const workspaceId = lifecycle.workspaceId.trim();
      const projectId = lifecycle.projectId.trim();
      const siteId = lifecycle.siteId.trim();
      let analysisId = lifecycle.analysisId.trim();

      if (hasLifecycleContext && (!workspaceId || !projectId)) {
        throw new Error("Workspace ID and Project ID are required when lifecycle tracking is enabled.");
      }

      if (hasLifecycleContext && !analysisId) {
        const created = await createAnalysisLifecycleRecord({
          workspaceId,
          projectId,
          siteId: siteId || undefined,
          name: lifecycle.analysisName.trim() || "Shared harness analysis",
          skillName: analysisType,
          metadata: {
            source_mode: sourceMode,
            created_from: "harness_analyst_workbench",
          },
        });
        analysisId = created.id;
      }

      const next = await runLifecycleAwareHarnessAnalysis({
        address,
        analysisType,
        sourceMode,
        assumptions: DEFAULT_ASSUMPTIONS,
        workspaceId: hasLifecycleContext ? workspaceId : undefined,
        projectId: hasLifecycleContext ? projectId : undefined,
        siteId: hasLifecycleContext ? siteId || undefined : undefined,
        analysisId: hasLifecycleContext ? analysisId || undefined : undefined,
      });
      setResult(next);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Harness run failed");
      setResult(null);
    } finally {
      setRunning(false);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-7xl flex-col gap-6 px-6 py-8">
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)] p-6 shadow-[var(--shadow-card)]">
        <div className="flex flex-col gap-2">
          <span className="section-pill">Analyst workbench</span>
          <h1 className="text-2xl font-semibold text-[var(--text-primary)]">Shared harness run</h1>
          <p className="max-w-3xl text-sm text-[var(--text-secondary)]">
            Run the same address to parcel, zoning, comps, and underwriting path used by the
            harness API, CLI, and chat surfaces.
          </p>
        </div>
        <form className="mt-6 grid gap-4 lg:grid-cols-[minmax(0,2fr),minmax(0,1fr),minmax(0,1fr),auto]" onSubmit={onSubmit}>
          <label className="flex flex-col gap-2 text-sm text-[var(--text-secondary)]">
            Address
            <input
              className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface-raised)] px-4 py-3 text-[var(--text-primary)] outline-none transition focus:border-[var(--brand)]"
              value={address}
              onChange={(event) => setAddress(event.target.value)}
            />
          </label>
          <label className="flex flex-col gap-2 text-sm text-[var(--text-secondary)]">
            Analysis
            <select
              className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface-raised)] px-4 py-3 text-[var(--text-primary)]"
              value={analysisType}
              onChange={(event) => setAnalysisType(event.target.value as AnalysisType)}
            >
              <option value="acquisition_memo">Acquisition memo</option>
              <option value="zoning_research">Zoning research</option>
              <option value="lender_package">Lender package</option>
            </select>
          </label>
          <fieldset className="flex flex-col gap-2 text-sm text-[var(--text-secondary)]">
            <legend className="mb-2">Source mode</legend>
            <div className="grid grid-cols-2 gap-2">
              {(["live", "fixture"] as const).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  onClick={() => setSourceMode(mode)}
                  className={`rounded-xl border px-3 py-3 text-sm font-medium transition ${
                    sourceMode === mode
                      ? "border-[var(--brand)] bg-[var(--brand-subtle)] text-[var(--brand)]"
                      : "border-[var(--border)] bg-[var(--bg-surface-raised)] text-[var(--text-secondary)]"
                  }`}
                >
                  {mode === "live" ? "Live" : "Fixture"}
                </button>
              ))}
            </div>
          </fieldset>
          <button
            type="submit"
            disabled={running || address.trim().length < 3}
            className="rounded-xl bg-[var(--text-primary)] px-5 py-3 text-sm font-medium text-[var(--bg-surface)] transition hover:opacity-90 disabled:opacity-40 lg:self-end"
          >
            {running ? "Running..." : "Run harness"}
          </button>
          <HarnessLifecycleContextFields value={lifecycle} onChange={setLifecycle} />
        </form>
        {error ? <p className="mt-4 text-sm text-[var(--danger)]">{error}</p> : null}
      </section>

      {result ? <HarnessAnalystRunSummary result={result} warnings={warnings} /> : null}
    </main>
  );
}
