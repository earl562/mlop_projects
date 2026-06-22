"use client";

import { Target } from "lucide-react";

import type { AgentRunTraceOpportunity } from "@/lib/agentRunTrace";

export default function AgentRunTraceOpportunities({
  opportunities,
}: {
  readonly opportunities: readonly AgentRunTraceOpportunity[];
}) {
  if (opportunities.length === 0) return null;

  return (
    <section className="mt-3" data-testid="agent-run-opportunities">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Target className="h-4 w-4 text-[var(--brand)]" aria-hidden="true" />
          <h5 className="text-xs font-semibold text-[var(--text-primary)]">
            Opportunity hypotheses
          </h5>
        </div>
        <span className="rounded-full border border-[var(--border-soft)] px-2 py-0.5 text-[10px] font-semibold text-[var(--text-secondary)]">
          {opportunityCountLabel(opportunities.length)}
        </span>
      </div>

      <div className="space-y-2">
        {opportunities.map((opportunity) => (
          <OpportunityRow key={opportunity.key} opportunity={opportunity} />
        ))}
      </div>
    </section>
  );
}

function OpportunityRow({
  opportunity,
}: {
  readonly opportunity: AgentRunTraceOpportunity;
}) {
  return (
    <article className="rounded-lg border border-[var(--border-soft)] bg-[var(--bg-surface)] px-3 py-2">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="font-mono text-[10px] font-semibold text-[var(--text-muted)]">
            {opportunity.key}
          </div>
          <h6 className="mt-1 text-xs font-semibold text-[var(--text-primary)]">
            {opportunity.proposed_scenario}
          </h6>
        </div>
        <span className="rounded-full border border-[var(--warning)] bg-[var(--brand-subtle)] px-2 py-0.5 text-[10px] font-semibold text-[var(--warning)]">
          {opportunity.status}
        </span>
      </div>

      <div className="mt-2 grid gap-2 text-xs leading-5 text-[var(--text-secondary)] sm:grid-cols-2">
        <OpportunityFact label="Verified condition" value={opportunity.current_verified_condition} />
        <OpportunityFact label="Upside mechanism" value={opportunity.upside_mechanism} />
        <OpportunityFact
          label="Zoning path"
          value={opportunity.required_zoning_entitlement_path}
        />
        <OpportunityFact label="Next verification" value={opportunity.next_verification_step} />
      </div>

      <div className="mt-2 flex flex-wrap gap-1.5">
        <OpportunityChip value={`confidence ${Math.round(opportunity.confidence * 100)}%`} />
        {opportunity.calculation_outputs.map((output) => (
          <OpportunityChip key={`${opportunity.key}-calc-${output}`} value={output} />
        ))}
        {opportunity.evidence_ids.map((evidenceId) => (
          <OpportunityChip key={`${opportunity.key}-evidence-${evidenceId}`} value={evidenceId} />
        ))}
      </div>

      <OpportunityList title="Blocking constraints" items={opportunity.blocking_constraints} />
      <OpportunityList title="Assumptions" items={opportunity.assumptions} />
    </article>
  );
}

function OpportunityFact({ label, value }: { readonly label: string; readonly value: string }) {
  return (
    <div>
      <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
        {label}
      </div>
      <div className="mt-0.5 text-[var(--text-primary)]">{value}</div>
    </div>
  );
}

function OpportunityList({
  title,
  items,
}: {
  readonly title: string;
  readonly items: readonly string[];
}) {
  return (
    <div className="mt-2">
      <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
        {title}
      </div>
      <div className="mt-1 flex flex-wrap gap-1.5">
        {items.map((item) => (
          <OpportunityChip key={`${title}-${item}`} value={item} />
        ))}
      </div>
    </div>
  );
}

function OpportunityChip({ value }: { readonly value: string }) {
  return (
    <span className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-inset)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-secondary)]">
      {value}
    </span>
  );
}

function opportunityCountLabel(count: number): string {
  return count === 1 ? "1 hypothesis" : `${count} hypotheses`;
}
