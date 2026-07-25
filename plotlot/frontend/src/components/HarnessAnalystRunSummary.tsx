import type { HarnessRunResultData } from "@/lib/api";
import {
  parseAcquisitionGuidance,
  parseCompSupportSummary,
  prettifyHarnessValue,
} from "@/lib/harness-guidance";

interface Props {
  readonly result: HarnessRunResultData;
  readonly warnings: readonly string[];
}

type CompSearchStrategySummary = {
  readonly selectedMonths: number | null;
  readonly selectedReason: string;
};

function metricTone(value: string) {
  if (value.includes("passed")) return "text-[var(--success)]";
  if (value.includes("fail") || value.includes("block")) return "text-[var(--danger)]";
  return "text-[var(--warning)]";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function parseCompSearchStrategySummary(
  artifacts: Record<string, unknown>,
): CompSearchStrategySummary | null {
  const raw = artifacts.comp_search_strategy;
  if (!isRecord(raw)) return null;

  const selectedReason = typeof raw.selected_reason === "string" && raw.selected_reason.length > 0
    ? raw.selected_reason.replaceAll("_", " ")
    : null;
  const selectedMonths = typeof raw.selected_months === "number" && Number.isFinite(raw.selected_months)
    ? raw.selected_months
    : null;

  if (selectedReason === null && selectedMonths === null) return null;

  return {
    selectedMonths,
    selectedReason: selectedReason ?? "selection unavailable",
  };
}

export function HarnessAnalystRunSummary({ result, warnings }: Props) {
  const compSearchStrategy = parseCompSearchStrategySummary(result.artifacts);
  const acquisitionGuidance = parseAcquisitionGuidance(result.artifacts);
  const compSupportSummary = parseCompSupportSummary(result.artifacts);

  return (
    <>
      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {[
          ["Run status", result.status],
          ["Verification", result.verification_status],
          ["Evidence", String(result.evidence_items.length)],
          ["Calculations", String(result.calculations.length)],
        ].map(([label, value]) => (
          <article key={label} className="rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)] p-5 shadow-[var(--shadow-card)]">
            <p className="text-xs uppercase tracking-[0.08em] text-[var(--text-muted)]">{label}</p>
            <p className={`mt-3 text-lg font-semibold ${label === "Verification" ? metricTone(value) : "text-[var(--text-primary)]"}`}>{value}</p>
          </article>
        ))}
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.5fr),minmax(0,1fr)]">
        <article className="rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)] p-6 shadow-[var(--shadow-card)]">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold text-[var(--text-primary)]">Claims</h2>
              <p className="mt-1 text-sm text-[var(--text-secondary)]">Material output from the shared run.</p>
            </div>
            <span className="section-pill">{result.analysis_type.replaceAll("_", " ")}</span>
          </div>
          <div className="mt-5 space-y-3">
            {result.claims.map((claim) => (
              <div key={claim.claim_id} className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface-raised)] p-4">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-medium text-[var(--text-primary)]">{claim.claim_type.replaceAll("_", " ")}</p>
                  <p className="text-xs text-[var(--text-muted)]">{Math.round(claim.confidence * 100)}% confidence</p>
                </div>
                <p className="mt-2 text-sm text-[var(--text-secondary)]">{claim.claim_text}</p>
              </div>
            ))}
          </div>
        </article>

        <article className="rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)] p-6 shadow-[var(--shadow-card)]">
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">Run metadata</h2>
          <dl className="mt-5 space-y-3 text-sm">
            <div className="flex items-center justify-between gap-3">
              <dt className="text-[var(--text-muted)]">Run ID</dt>
              <dd className="font-mono text-xs text-[var(--text-primary)]">{result.run_id}</dd>
            </div>
            {result.analysis_run_id ? (
              <div className="flex items-center justify-between gap-3">
                <dt className="text-[var(--text-muted)]">Analysis run ID</dt>
                <dd className="font-mono text-xs text-[var(--text-primary)]">{result.analysis_run_id}</dd>
              </div>
            ) : null}
            <div className="flex items-center justify-between gap-3">
              <dt className="text-[var(--text-muted)]">Report ID</dt>
              <dd className="font-mono text-xs text-[var(--text-primary)]">{result.report_id}</dd>
            </div>
            <div className="flex items-center justify-between gap-3">
              <dt className="text-[var(--text-muted)]">Source mode</dt>
              <dd className="text-[var(--text-primary)]">{result.source_mode}</dd>
            </div>
            <div className="flex items-center justify-between gap-3">
              <dt className="text-[var(--text-muted)]">Preliminary</dt>
              <dd className="text-[var(--text-primary)]">{result.preliminary ? "Yes" : "No"}</dd>
            </div>
          </dl>
          {compSearchStrategy ? (
            <div className="mt-5 rounded-xl border border-[var(--border)] bg-[var(--bg-surface-raised)] p-4">
              <p className="text-xs uppercase tracking-[0.08em] text-[var(--text-muted)]">Comp search strategy</p>
              <p className="mt-2 text-sm text-[var(--text-primary)]">{compSearchStrategy.selectedReason}</p>
              {compSearchStrategy.selectedMonths !== null ? (
                <p className="mt-1 text-sm text-[var(--text-secondary)]">
                  Selected window: {compSearchStrategy.selectedMonths} months
                </p>
              ) : null}
            </div>
          ) : null}
          {acquisitionGuidance ? (
            <div className="mt-5 rounded-xl border border-[var(--border)] bg-[var(--bg-surface-raised)] p-4">
              <p className="text-xs uppercase tracking-[0.08em] text-[var(--text-muted)]">Market signal</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <span className="rounded-full border border-[var(--border)] px-3 py-1 text-xs font-medium text-[var(--text-primary)]">
                  {prettifyHarnessValue(acquisitionGuidance.marketSignalVerificationStatus)}
                </span>
                <span className="rounded-full border border-[var(--border)] px-3 py-1 text-xs font-medium text-[var(--text-primary)]">
                  {acquisitionGuidance.recommendationConfidence} confidence
                </span>
                <span className="rounded-full border border-[var(--border)] px-3 py-1 text-xs font-medium text-[var(--text-primary)]">
                  {prettifyHarnessValue(acquisitionGuidance.recommendedAction)}
                </span>
              </div>
              <p className="mt-3 text-sm text-[var(--text-secondary)]">
                Basis: {prettifyHarnessValue(acquisitionGuidance.basis)}
              </p>
              <p className="mt-1 text-sm text-[var(--text-secondary)]">
                Land signal: {prettifyHarnessValue(acquisitionGuidance.landSignalStrength)}
              </p>
              <p className="mt-1 text-sm text-[var(--text-secondary)]">
                Validation: {acquisitionGuidance.requiresMarketSignalValidation ? "Required" : "Not required"}
              </p>
            </div>
          ) : null}
          {compSupportSummary ? (
            <div className="mt-5 rounded-xl border border-[var(--border)] bg-[var(--bg-surface-raised)] p-4">
              <p className="text-xs uppercase tracking-[0.08em] text-[var(--text-muted)]">Comp support</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <span className={`rounded-full border border-[var(--border)] px-3 py-1 text-xs font-medium ${metricTone(compSupportSummary.status)}`}>
                  {prettifyHarnessValue(compSupportSummary.status)}
                </span>
                <span className="rounded-full border border-[var(--border)] px-3 py-1 text-xs font-medium text-[var(--text-primary)]">
                  {compSupportSummary.recommendationConfidence} confidence
                </span>
              </div>
              <p className="mt-3 text-sm text-[var(--text-secondary)]">
                Reason: {compSupportSummary.reason}
              </p>
              <p className="mt-1 text-sm text-[var(--text-secondary)]">
                Land tier: {prettifyHarnessValue(compSupportSummary.landSignalTier)}
              </p>
              <p className="mt-1 text-sm text-[var(--text-secondary)]">
                Public listing tier: {prettifyHarnessValue(compSupportSummary.publicListingSignalTier)}
              </p>
              <p className="mt-1 text-sm text-[var(--text-secondary)]">
                Validation: {compSupportSummary.requiresMarketSignalValidation ? "Required" : "Not required"}
              </p>
            </div>
          ) : null}
          {warnings.length > 0 ? (
            <div className="mt-5 rounded-xl border border-[var(--brand-soft-border)] bg-[var(--brand-subtle)] p-4">
              <p className="text-sm font-medium text-[var(--brand)]">Warnings</p>
              <ul className="mt-2 space-y-2 text-sm text-[var(--text-secondary)]">
                {warnings.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </article>
      </section>

      <section className="grid gap-4 xl:grid-cols-3">
        <article className="rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)] p-6 shadow-[var(--shadow-card)]">
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">Evidence</h2>
          <div className="mt-4 space-y-3">
            {result.evidence_items.slice(0, 6).map((item) => (
              <div key={item.evidence_id} className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface-raised)] p-4">
                <p className="text-sm font-medium text-[var(--text-primary)]">{item.source_type.replaceAll("_", " ")}</p>
                <p className="mt-1 text-sm text-[var(--text-secondary)]">{item.source_name}</p>
                <p className="mt-2 text-xs text-[var(--text-muted)]">
                  {item.source_identifier} • {item.applicability} • {item.freshness_status}
                </p>
              </div>
            ))}
          </div>
        </article>
        <article className="rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)] p-6 shadow-[var(--shadow-card)]">
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">Calculations</h2>
          <div className="mt-4 space-y-3">
            {result.calculations.map((item) => (
              <div key={item.calculation_id} className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface-raised)] p-4">
                <p className="text-sm font-medium text-[var(--text-primary)]">{item.calculation_type.replaceAll("_", " ")}</p>
                <p className="mt-1 text-xs font-mono text-[var(--text-muted)]">{item.formula_version}</p>
              </div>
            ))}
          </div>
        </article>
        <article className="rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)] p-6 shadow-[var(--shadow-card)]">
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">Events</h2>
          <div className="mt-4 space-y-3">
            {result.events.slice(-8).map((item) => (
              <div key={item.event_id} className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface-raised)] p-4">
                <p className="text-sm font-medium text-[var(--text-primary)]">{item.type}</p>
                <p className="mt-1 text-xs text-[var(--text-muted)]">{item.source} {item.status ? `• ${item.status}` : ""}</p>
              </div>
            ))}
          </div>
        </article>
      </section>
    </>
  );
}
