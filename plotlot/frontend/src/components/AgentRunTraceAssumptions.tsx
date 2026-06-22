"use client";

import { AlertTriangle } from "lucide-react";

import type { AgentRunTraceAssumption } from "@/lib/agentRunTraceTypes";

export default function AgentRunTraceAssumptions({
  assumptions,
}: {
  readonly assumptions: readonly AgentRunTraceAssumption[];
}) {
  if (assumptions.length === 0) return null;

  return (
    <div className="mt-3" data-testid="agent-run-artifact-assumptions">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-[var(--warning)]" aria-hidden="true" />
          <h5 className="text-xs font-semibold text-[var(--text-primary)]">
            Artifact assumptions
          </h5>
        </div>
        <span className="rounded-full border border-[var(--warning)] bg-[var(--brand-subtle)] px-2 py-0.5 text-[10px] font-semibold text-[var(--warning)]">
          {assumptionCountLabel(assumptions.length)}
        </span>
      </div>

      <div className="space-y-2">
        {assumptions.map((assumption) => (
          <AssumptionRow key={assumption.key} assumption={assumption} />
        ))}
      </div>
    </div>
  );
}

function AssumptionRow({
  assumption,
}: {
  readonly assumption: AgentRunTraceAssumption;
}) {
  return (
    <div className="rounded-lg border border-[var(--warning)] bg-[var(--brand-subtle)] px-3 py-2">
      <div className="flex flex-wrap items-center gap-1.5">
        <AssumptionChip value={assumption.status} />
        <AssumptionChip value={assumption.source} />
        <AssumptionChip value={assumption.field_key ?? "No field key"} />
      </div>
      <p className="mt-2 text-xs leading-5 text-[var(--text-primary)]">{assumption.text}</p>
      <div className="mt-1 font-mono text-[10px] text-[var(--text-muted)]">{assumption.key}</div>
    </div>
  );
}

function AssumptionChip({ value }: { readonly value: string }) {
  return (
    <span className="rounded-full border border-[var(--warning)] bg-[var(--bg-surface)] px-2 py-0.5 text-[10px] font-medium text-[var(--warning)]">
      {value}
    </span>
  );
}

function assumptionCountLabel(count: number): string {
  return count === 1 ? "1 assumption" : `${count} assumptions`;
}
