"use client";

import { AlertTriangle, CheckCircle2, Clock3, HelpCircle } from "lucide-react";

import type { LookupSnapshotData, LookupSnapshotFieldData } from "@/lib/agentRuns";
import AgentRunSnapshotEvidenceDetails from "./AgentRunSnapshotEvidenceDetails";

type FieldDisplayState =
  | "verified"
  | "assumed"
  | "stale"
  | "contradicted"
  | "unknown"
  | "requires_human_review";

type StateCounts = Readonly<Record<FieldDisplayState, number>>;

export default function AgentRunSnapshotEvidence({
  snapshot,
}: {
  readonly snapshot: LookupSnapshotData | null;
}) {
  if (!snapshot || snapshot.fields.length === 0) return null;
  const counts = stateCounts(snapshot.fields);

  return (
    <div className="mt-4 border-t border-[var(--border-soft)] pt-3" data-testid="agent-run-snapshot-fields">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-xs font-semibold text-[var(--text-primary)]">
          Lookup evidence workbench
        </h4>
        <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
          {snapshot.fields.length} fields
        </span>
      </div>
      <div className="mb-3 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        <StateCount label="Verified" value={counts.verified} state="verified" />
        <StateCount label="Assumed" value={counts.assumed} state="assumed" />
        <StateCount label="Stale" value={counts.stale} state="stale" />
        <StateCount
          label="Review"
          value={counts.requires_human_review}
          state="requires_human_review"
        />
        <StateCount label="Contradicted" value={counts.contradicted} state="contradicted" />
        <StateCount label="Unknown" value={counts.unknown} state="unknown" />
      </div>
      <div className="max-h-28 overflow-y-auto border-y border-[var(--border-soft)]">
        {snapshot.fields.map((field) => (
          <SnapshotFieldRow field={field} key={field.key} />
        ))}
      </div>
      <AgentRunSnapshotEvidenceDetails
        calculations={snapshot.calculations}
        sources={snapshot.source_metadata}
      />
    </div>
  );
}

function StateCount({
  label,
  value,
  state,
}: {
  readonly label: string;
  readonly value: number;
  readonly state: FieldDisplayState;
}) {
  return (
    <div className="min-h-[52px] rounded-lg bg-[var(--bg-surface)] px-2.5 py-2">
      <div className={statePillClass(state)}>
        {stateIcon(state)}
        {label}
      </div>
      <div className="mt-1 font-mono text-sm font-semibold text-[var(--text-primary)]">
        {value}
      </div>
    </div>
  );
}

function SnapshotFieldRow({ field }: { readonly field: LookupSnapshotFieldData }) {
  const displayState = normalizeDisplayState(field.display_state);
  return (
    <div className="grid grid-cols-[minmax(0,1fr)_minmax(8rem,auto)] gap-2 border-b border-[var(--border-soft)] py-1.5 last:border-b-0 sm:grid-cols-[minmax(0,1fr)_minmax(12rem,auto)]">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold text-[var(--text-primary)]">
            {field.label || field.key}
          </span>
          <span className={statePillClass(displayState)}>
            {stateIcon(displayState)}
            {displayStateLabel(displayState)}
          </span>
        </div>
        <div className="mt-1 truncate font-mono text-xs text-[var(--text-secondary)]" title={formatFieldValue(field)}>
          {formatFieldValue(field)}
        </div>
        <div className="mt-1 flex flex-wrap gap-1 text-[10px] text-[var(--text-muted)]">
          <span>freshness: {field.freshness || "unknown"}</span>
          <span>failure: {field.failure_behavior || "unknown"}</span>
        </div>
      </div>
      <div className="min-w-0 text-right text-xs text-[var(--text-muted)]">
        <div className="font-mono font-semibold text-[var(--text-primary)]">
          {formatConfidence(field.confidence)}
        </div>
        <div className="mt-1 flex flex-wrap justify-end gap-1">
          {field.evidence_ids.length > 0 ? (
            field.evidence_ids.map((evidenceId) => (
              <span
                className="rounded border border-[var(--border-soft)] px-1.5 py-0.5 font-mono text-[10px]"
                key={evidenceId}
              >
                {evidenceId}
              </span>
            ))
          ) : (
            <span className="text-[var(--danger)]">No evidence ID</span>
          )}
        </div>
        {field.warnings.length > 0 && (
          <div className="mt-1 text-[var(--warning)]">
            {field.warnings.join("; ")}
          </div>
        )}
      </div>
    </div>
  );
}

function normalizeDisplayState(value: string): FieldDisplayState {
  switch (value.toLowerCase()) {
    case "verified":
      return "verified";
    case "assumed":
      return "assumed";
    case "stale":
      return "stale";
    case "contradicted":
      return "contradicted";
    case "unknown":
      return "unknown";
    case "requires_human_review":
      return "requires_human_review";
    default:
      return "unknown";
  }
}

function formatFieldValue(field: LookupSnapshotFieldData): string {
  if (field.value === null) return "Unknown";
  const value = String(field.value);
  return field.unit ? `${value} ${field.unit}` : value;
}

function formatConfidence(value: number): string {
  return `${Math.round(value * 100)}% confidence`;
}

function displayStateLabel(state: FieldDisplayState): string {
  switch (state) {
    case "verified":
      return "verified";
    case "assumed":
      return "assumed";
    case "stale":
      return "stale";
    case "contradicted":
      return "contradicted";
    case "unknown":
      return "unknown";
    case "requires_human_review":
      return "human review";
  }
}

function statePillClass(state: FieldDisplayState): string {
  const base = "inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold";
  switch (state) {
    case "verified":
      return `${base} border-[var(--success)] bg-[var(--success-subtle)] text-[var(--success)]`;
    case "assumed":
    case "stale":
    case "requires_human_review":
      return `${base} border-[var(--warning)] bg-[var(--brand-subtle)] text-[var(--warning)]`;
    case "contradicted":
      return `${base} border-[var(--danger)] bg-[var(--danger-subtle)] text-[var(--danger)]`;
    case "unknown":
      return `${base} border-[var(--border)] bg-[var(--bg-surface)] text-[var(--text-muted)]`;
  }
}

function stateIcon(state: FieldDisplayState) {
  switch (state) {
    case "verified":
      return <CheckCircle2 className="h-3 w-3" aria-hidden="true" />;
    case "assumed":
    case "stale":
      return <Clock3 className="h-3 w-3" aria-hidden="true" />;
    case "contradicted":
    case "requires_human_review":
      return <AlertTriangle className="h-3 w-3" aria-hidden="true" />;
    case "unknown":
      return <HelpCircle className="h-3 w-3" aria-hidden="true" />;
  }
}

function stateCounts(fields: readonly LookupSnapshotFieldData[]): StateCounts {
  const counts: Record<FieldDisplayState, number> = {
    verified: 0,
    assumed: 0,
    stale: 0,
    contradicted: 0,
    unknown: 0,
    requires_human_review: 0,
  };
  for (const field of fields) {
    counts[normalizeDisplayState(field.display_state)] += 1;
  }
  return counts;
}
