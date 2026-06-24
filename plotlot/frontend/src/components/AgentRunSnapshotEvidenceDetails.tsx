"use client";

import { ExternalLink } from "lucide-react";

import type {
  LookupSnapshotCalculationData,
  LookupSnapshotSourceMetadataData,
} from "@/lib/agentRuns";
import SafeExternalLink from "./SafeExternalLink";

export default function AgentRunSnapshotEvidenceDetails({
  calculations,
  sources,
}: {
  readonly calculations: readonly LookupSnapshotCalculationData[];
  readonly sources: readonly LookupSnapshotSourceMetadataData[];
}) {
  return (
    <>
      <CalculationList calculations={calculations} />
      <SourceMetadataList sources={sources} />
    </>
  );
}

function CalculationList({
  calculations,
}: {
  readonly calculations: readonly LookupSnapshotCalculationData[];
}) {
  if (calculations.length === 0) return null;
  return (
    <div className="mt-3 border-t border-[var(--border-soft)] pt-3">
      <h5 className="text-xs font-semibold text-[var(--text-primary)]">Deterministic calculations</h5>
      <div className="mt-2 grid gap-2">
        {calculations.map((calculation) => (
          <div className="rounded-lg bg-[var(--bg-surface)] px-3 py-2" key={calculation.output_label}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-mono text-xs font-semibold text-[var(--text-primary)]">
                {calculation.output_label}
              </span>
              <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
                {calculation.calculator_name} v{calculation.calculator_version}
              </span>
            </div>
            <div className="mt-1 text-xs text-[var(--text-secondary)]">{calculation.formula}</div>
            <EvidenceIdList evidenceIds={calculation.input_evidence_ids} />
          </div>
        ))}
      </div>
    </div>
  );
}

function SourceMetadataList({
  sources,
}: {
  readonly sources: readonly LookupSnapshotSourceMetadataData[];
}) {
  if (sources.length === 0) return null;
  return (
    <div className="mt-3 border-t border-[var(--border-soft)] pt-3">
      <h5 className="text-xs font-semibold text-[var(--text-primary)]">Recorded sources</h5>
      <div className="mt-2 grid gap-2">
        {sources.map((source) => (
          <div className="rounded-lg bg-[var(--bg-surface)] px-3 py-2" key={source.evidence_id}>
            <SafeExternalLink
              className="inline-flex max-w-full items-center gap-1 text-xs font-semibold text-[var(--text-primary)] underline-offset-2 hover:text-[var(--brand)] hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand)]"
              href={source.source_url}
            >
              <span className="truncate">{source.source_title || source.evidence_id}</span>
              <ExternalLink className="h-3 w-3 shrink-0" aria-hidden="true" />
            </SafeExternalLink>
            <div className="mt-1 flex flex-wrap gap-2 font-mono text-[10px] text-[var(--text-muted)]">
              <span>{source.evidence_id}</span>
              {source.effective_date && <span>effective {source.effective_date}</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function EvidenceIdList({ evidenceIds }: { readonly evidenceIds: readonly string[] }) {
  return (
    <div className="mt-1 flex flex-wrap gap-1">
      {evidenceIds.length > 0 ? (
        evidenceIds.map((evidenceId) => (
          <span
            className="rounded border border-[var(--border-soft)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--text-muted)]"
            key={evidenceId}
          >
            {evidenceId}
          </span>
        ))
      ) : (
        <span className="text-xs text-[var(--danger)]">No evidence ID</span>
      )}
    </div>
  );
}
