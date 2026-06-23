"use client";

import { Database, ExternalLink } from "lucide-react";

import type { AgentRunTraceSourceRetrieval } from "@/lib/agentRunTrace";
import SafeExternalLink from "./SafeExternalLink";

export default function AgentRunSourceRetrievals({
  retrievals,
}: {
  readonly retrievals: readonly AgentRunTraceSourceRetrieval[];
}) {
  if (retrievals.length === 0) return null;

  return (
    <div className="mt-3" data-testid="agent-run-source-retrievals">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Database className="h-4 w-4 text-[var(--brand)]" aria-hidden="true" />
          <h5 className="text-xs font-semibold text-[var(--text-primary)]">Source retrievals</h5>
        </div>
        <span className="rounded-full border border-[var(--border-soft)] px-2 py-0.5 text-[10px] font-semibold text-[var(--text-secondary)]">
          {retrievalCountLabel(retrievals.length)}
        </span>
      </div>

      <div className="space-y-2">
        {retrievals.map((retrieval) => (
          <SourceRetrievalRow key={retrieval.evidence_id} retrieval={retrieval} />
        ))}
      </div>
    </div>
  );
}

function SourceRetrievalRow({
  retrieval,
}: {
  readonly retrieval: AgentRunTraceSourceRetrieval;
}) {
  const flags = [...retrieval.quality_flags, ...retrieval.warnings];
  return (
    <div className="rounded-lg border border-[var(--border-soft)] bg-[var(--bg-surface)] px-3 py-2">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <SafeExternalLink
            href={retrieval.source_url}
            className="inline-flex max-w-full items-center gap-1 text-xs font-semibold text-[var(--text-primary)] underline-offset-2 hover:underline"
          >
            <span className="truncate">{retrieval.source_title}</span>
            <ExternalLink className="h-3 w-3 shrink-0 text-[var(--text-muted)]" aria-hidden="true" />
          </SafeExternalLink>
          <div className="mt-1 flex flex-wrap gap-1.5 text-[10px] text-[var(--text-secondary)]">
            <span className="font-mono">{retrieval.evidence_id}</span>
            <span>{retrieval.publisher}</span>
            <span>{retrieval.source_type}</span>
          </div>
        </div>
        <span className={retrievalQualityClass(retrieval)}>
          {formatScore(retrieval.quality_score)} source
        </span>
      </div>

      <div className="mt-2 grid gap-2 text-[10px] text-[var(--text-secondary)] sm:grid-cols-2">
        <RetrievalFact label="Raw" value={retrieval.raw_artifact_ref} />
        <RetrievalFact label="Retrieved" value={retrieval.retrieved_at} />
        <RetrievalFact label="Query" value={retrieval.query_parameters.join(", ") || "None"} />
        <RetrievalFact label="Effective" value={retrieval.effective_date} />
      </div>

      <div className="mt-2 flex flex-wrap gap-1.5">
        {retrieval.lineage.map((item) => (
          <TraceChip key={`${retrieval.evidence_id}-lineage-${item}`} value={item} tone="neutral" />
        ))}
        {flags.length === 0 ? (
          <TraceChip value="No retrieval warnings" tone="success" />
        ) : (
          flags.map((item) => (
            <TraceChip key={`${retrieval.evidence_id}-flag-${item}`} value={item} tone="warning" />
          ))
        )}
      </div>
    </div>
  );
}

function RetrievalFact({ label, value }: { readonly label: string; readonly value: string }) {
  return (
    <div className="min-w-0">
      <span className="font-semibold text-[var(--text-primary)]">{label}</span>
      <span className="mx-1 text-[var(--text-muted)]">/</span>
      <span className="break-words font-mono">{value}</span>
    </div>
  );
}

function TraceChip({
  value,
  tone,
}: {
  readonly value: string;
  readonly tone: "neutral" | "success" | "warning";
}) {
  return <span className={traceChipClass(tone)}>{value}</span>;
}

function retrievalCountLabel(count: number): string {
  return count === 1 ? "1 retrieval" : `${count} retrievals`;
}

function formatScore(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function retrievalQualityClass(retrieval: AgentRunTraceSourceRetrieval): string {
  const base = "rounded-full border px-2 py-0.5 text-[10px] font-semibold";
  if (retrieval.quality_score >= 0.9 && retrieval.warnings.length === 0) {
    return `${base} border-[var(--success)] bg-[var(--success-subtle)] text-[var(--success)]`;
  }
  if (retrieval.quality_score >= 0.75) {
    return `${base} border-[var(--warning)] bg-[var(--brand-subtle)] text-[var(--warning)]`;
  }
  return `${base} border-[var(--danger)] bg-[var(--danger-subtle)] text-[var(--danger)]`;
}

function traceChipClass(tone: "neutral" | "success" | "warning"): string {
  const base = "rounded-full border px-2 py-0.5 text-[10px] font-medium";
  if (tone === "success") {
    return `${base} border-[var(--success)] bg-[var(--success-subtle)] text-[var(--success)]`;
  }
  if (tone === "warning") {
    return `${base} border-[var(--warning)] bg-[var(--brand-subtle)] text-[var(--warning)]`;
  }
  return `${base} border-[var(--border-soft)] text-[var(--text-secondary)]`;
}
