"use client";

import { useEffect, useState } from "react";

import {
  type HarnessRunEventData,
  type HarnessRunResultData,
  type HarnessRunVerificationData,
  getHarnessRun,
  getHarnessRunEvents,
  getHarnessRunVerification,
} from "@/lib/api";
import {
  parseAcquisitionGuidance,
  parseCompSupportSummary,
  prettifyHarnessValue,
} from "@/lib/harness-guidance";
import HarnessCompSearchStrategy from "@/components/HarnessCompSearchStrategy";
import HarnessPipelineStageChain from "@/components/HarnessPipelineStageChain";

function statusTone(value: string) {
  const normalized = value.toLowerCase();
  if (normalized.includes("pass") || normalized.includes("complete")) return "text-[var(--success)]";
  if (normalized.includes("fail") || normalized.includes("block")) return "text-[var(--danger)]";
  return "text-[var(--warning)]";
}

type Props = {
  runId: string;
  projectId: string;
  siteId: string;
};

export default function HarnessRunDetail({ runId, projectId, siteId }: Props) {
  const [run, setRun] = useState<HarnessRunResultData | null>(null);
  const [verification, setVerification] = useState<HarnessRunVerificationData | null>(null);
  const [events, setEvents] = useState<HarnessRunEventData[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const [runResult, eventResult, verificationResult] = await Promise.all([
          getHarnessRun(runId),
          getHarnessRunEvents(runId),
          getHarnessRunVerification(runId).catch(() => null),
        ]);
        if (cancelled) return;
        setRun(runResult);
        setEvents(eventResult.events);
        setVerification(verificationResult);
      } catch (caught) {
        if (cancelled) return;
        setError(caught instanceof Error ? caught.message : "Failed to load harness run");
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [runId]);

  if (error) {
    return (
      <main className="mx-auto max-w-5xl px-6 py-8">
        <div className="rounded-2xl border border-[var(--danger)]/20 bg-[var(--danger-subtle)] p-6">
          <h1 className="text-xl font-semibold text-[var(--text-primary)]">Run unavailable</h1>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">{error}</p>
        </div>
      </main>
    );
  }

  if (!run) {
    return (
      <main className="mx-auto max-w-5xl px-6 py-8">
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)] p-6 shadow-[var(--shadow-card)]">
          <p className="text-sm text-[var(--text-secondary)]">Loading persisted harness run...</p>
        </div>
      </main>
    );
  }
  const acquisitionGuidance = parseAcquisitionGuidance(run.artifacts);
  const compSupportSummary = parseCompSupportSummary(run.artifacts);
  return (
    <main className="mx-auto flex max-w-6xl flex-col gap-6 px-6 py-8">
      <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)] p-6 shadow-[var(--shadow-card)]">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <span className="section-pill">Persisted run</span>
            <h1 className="mt-3 text-2xl font-semibold text-[var(--text-primary)]">Harness analysis detail</h1>
            <p className="mt-2 text-sm text-[var(--text-secondary)]">
              Run <span className="font-mono text-xs text-[var(--text-primary)]">{run.run_id}</span> for
              project <span className="font-mono text-xs text-[var(--text-primary)]"> {projectId}</span> and site
              <span className="font-mono text-xs text-[var(--text-primary)]"> {siteId}</span>.
            </p>
          </div>
          <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface-raised)] px-4 py-3 text-right">
            <p className="text-xs uppercase tracking-[0.08em] text-[var(--text-muted)]">Verification</p>
            <p className={`mt-2 text-sm font-semibold ${statusTone(verification?.status ?? run.verification_status)}`}>
              {verification?.status ?? run.verification_status}
            </p>
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {[
          ["Analysis", run.analysis_type],
          ["Run status", run.status],
          ["Source mode", run.source_mode],
          [
            "Market signal",
            acquisitionGuidance
              ? prettifyHarnessValue(acquisitionGuidance.marketSignalVerificationStatus)
              : "unavailable",
          ],
        ].map(([label, value]) => (
          <article key={label} className="rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)] p-5 shadow-[var(--shadow-card)]">
            <p className="text-xs uppercase tracking-[0.08em] text-[var(--text-muted)]">{label}</p>
            <p className={`mt-3 text-lg font-semibold ${label === "Run status" ? statusTone(value) : "text-[var(--text-primary)]"}`}>{value}</p>
          </article>
        ))}
      </section>

      {acquisitionGuidance ? (
        <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)] p-6 shadow-[var(--shadow-card)]">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold text-[var(--text-primary)]">Acquisition guidance</h2>
              <p className="mt-2 text-sm text-[var(--text-secondary)]">
                Recommendation quality from the shared parcel, zoning, comp, and underwriting path.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <span className="rounded-full border border-[var(--border)] px-3 py-1 text-xs font-medium text-[var(--text-primary)]">
                {acquisitionGuidance.recommendationConfidence} confidence
              </span>
              <span className="rounded-full border border-[var(--border)] px-3 py-1 text-xs font-medium text-[var(--text-primary)]">
                {prettifyHarnessValue(acquisitionGuidance.recommendedAction)}
              </span>
            </div>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {[
              ["Verification status", prettifyHarnessValue(acquisitionGuidance.marketSignalVerificationStatus)],
              ["Decision basis", prettifyHarnessValue(acquisitionGuidance.basis)],
              ["Land signal", prettifyHarnessValue(acquisitionGuidance.landSignalStrength)],
              ["Validation", acquisitionGuidance.requiresMarketSignalValidation ? "Required" : "Not required"],
            ].map(([label, value]) => (
              <div key={label} className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface-raised)] p-4">
                <p className="text-xs uppercase tracking-[0.08em] text-[var(--text-muted)]">{label}</p>
                <p className="mt-2 text-sm font-medium text-[var(--text-primary)]">{value}</p>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      {compSupportSummary ? (
        <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)] p-6 shadow-[var(--shadow-card)]">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <h2 className="text-lg font-semibold text-[var(--text-primary)]">Comparable support</h2>
              <p className="mt-2 text-sm text-[var(--text-secondary)]">
                Whether the offer path is grounded in direct land comps or thinner public listing support.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <span className={`rounded-full border border-[var(--border)] px-3 py-1 text-xs font-medium ${statusTone(compSupportSummary.status)}`}>
                {prettifyHarnessValue(compSupportSummary.status)}
              </span>
              <span className="rounded-full border border-[var(--border)] px-3 py-1 text-xs font-medium text-[var(--text-primary)]">
                {compSupportSummary.recommendationConfidence} confidence
              </span>
            </div>
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
            {[
              ["Support reason", compSupportSummary.reason],
              ["Recommended action", prettifyHarnessValue(compSupportSummary.recommendedAction)],
              ["Land signal tier", prettifyHarnessValue(compSupportSummary.landSignalTier)],
              ["Public listing tier", prettifyHarnessValue(compSupportSummary.publicListingSignalTier)],
            ].map(([label, value]) => (
              <div key={label} className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface-raised)] p-4">
                <p className="text-xs uppercase tracking-[0.08em] text-[var(--text-muted)]">{label}</p>
                <p className="mt-2 text-sm font-medium text-[var(--text-primary)]">{value}</p>
              </div>
            ))}
          </div>
          <p className="mt-4 text-sm text-[var(--text-secondary)]">
            Validation: {compSupportSummary.requiresMarketSignalValidation ? "Required" : "Not required"}
          </p>
        </section>
      ) : null}

      <HarnessPipelineStageChain stages={run.pipeline_stages} />
      <HarnessCompSearchStrategy artifacts={run.artifacts} />

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr),minmax(0,0.8fr)]">
        <article className="rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)] p-6 shadow-[var(--shadow-card)]">
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">Claims and evidence</h2>
          <div className="mt-4 space-y-3">
            {run.claims.map((claim) => (
              <div key={claim.claim_id} className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface-raised)] p-4">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-medium text-[var(--text-primary)]">{claim.claim_type.replaceAll("_", " ")}</p>
                  <p className="text-xs text-[var(--text-muted)]">{Math.round(claim.confidence * 100)}%</p>
                </div>
                <p className="mt-2 text-sm text-[var(--text-secondary)]">{claim.claim_text}</p>
              </div>
            ))}
          </div>
        </article>

        <article className="rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)] p-6 shadow-[var(--shadow-card)]">
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">Verification checklist</h2>
          <div className="mt-4 space-y-3">
            {verification
              ? Object.entries(verification.checks).map(([key, value]) => (
                  <div key={key} className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface-raised)] p-4">
                    <p className="text-sm font-medium text-[var(--text-primary)]">{key.replaceAll("_", " ")}</p>
                    <p className={`mt-1 text-sm ${statusTone(value)}`}>{value}</p>
                  </div>
                ))
              : <p className="text-sm text-[var(--text-secondary)]">No persisted verification detail found for this run.</p>}
          </div>
          {verification && (
            <div className="mt-4 space-y-2 text-sm text-[var(--text-secondary)]">
              {verification.missing_evidence.length > 0 ? <p>Missing evidence: {verification.missing_evidence.join(", ")}</p> : null}
              {verification.stale_evidence.length > 0 ? <p>Stale evidence: {verification.stale_evidence.join(", ")}</p> : null}
              {verification.unsupported_claims.length > 0 ? <p>Unsupported claims: {verification.unsupported_claims.join(", ")}</p> : null}
              {verification.mock_or_fixture_blockers.length > 0 ? <p>Fixture blockers: {verification.mock_or_fixture_blockers.join(", ")}</p> : null}
            </div>
          )}
        </article>
      </section>

      <section className="grid gap-4 xl:grid-cols-3">
        <article className="rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)] p-6 shadow-[var(--shadow-card)]">
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">Evidence</h2>
          <div className="mt-4 space-y-3">
            {run.evidence_items.slice(0, 8).map((item) => (
              <div key={item.evidence_id} className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface-raised)] p-4">
                <p className="text-sm font-medium text-[var(--text-primary)]">{item.source_name}</p>
                <p className="mt-1 text-xs text-[var(--text-muted)]">{item.source_type} • {item.source_identifier}</p>
              </div>
            ))}
          </div>
        </article>

        <article className="rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)] p-6 shadow-[var(--shadow-card)]">
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">Calculations</h2>
          <div className="mt-4 space-y-3">
            {run.calculations.map((item) => (
              <div key={item.calculation_id} className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface-raised)] p-4">
                <p className="text-sm font-medium text-[var(--text-primary)]">{item.calculation_type.replaceAll("_", " ")}</p>
                <p className="mt-1 text-xs font-mono text-[var(--text-muted)]">{item.formula_version}</p>
              </div>
            ))}
          </div>
        </article>

        <article className="rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)] p-6 shadow-[var(--shadow-card)]">
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">Event timeline</h2>
          <div className="mt-4 space-y-3">
            {events.slice(-10).map((event) => (
              <div key={event.event_id} className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface-raised)] p-4">
                <p className="text-sm font-medium text-[var(--text-primary)]">{event.type}</p>
                <p className="mt-1 text-xs text-[var(--text-muted)]">{event.source}{event.status ? ` • ${event.status}` : ""}</p>
              </div>
            ))}
          </div>
        </article>
      </section>
    </main>
  );
}
