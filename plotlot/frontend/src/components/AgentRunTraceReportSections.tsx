"use client";

import { FileText } from "lucide-react";

import type { AgentRunTraceReportClaim, AgentRunTraceReportSection } from "@/lib/agentRunTrace";

export default function AgentRunTraceReportSections({
  sections,
}: {
  readonly sections: readonly AgentRunTraceReportSection[];
}) {
  if (sections.length === 0) return null;

  return (
    <section className="mt-3" data-testid="agent-run-report-claims">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <FileText className="h-4 w-4 text-[var(--brand)]" aria-hidden="true" />
          <h5 className="text-xs font-semibold text-[var(--text-primary)]">Report claims</h5>
        </div>
        <span className="rounded-full border border-[var(--border-soft)] px-2 py-0.5 text-[10px] font-semibold text-[var(--text-secondary)]">
          {sectionCountLabel(sections.length)}
        </span>
      </div>

      <div className="space-y-2">
        {sections.map((section) => (
          <ReportSectionRow key={section.id} section={section} />
        ))}
      </div>
    </section>
  );
}

function ReportSectionRow({
  section,
}: {
  readonly section: AgentRunTraceReportSection;
}) {
  return (
    <article className="rounded-lg border border-[var(--border-soft)] bg-[var(--bg-surface)] px-3 py-2">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h6 className="text-xs font-semibold text-[var(--text-primary)]">{section.title}</h6>
          <div className="mt-1 font-mono text-[10px] text-[var(--text-muted)]">{section.id}</div>
        </div>
        <span className="rounded-full border border-[var(--border-soft)] px-2 py-0.5 text-[10px] font-semibold text-[var(--text-secondary)]">
          {claimCountLabel(section.claims.length)}
        </span>
      </div>

      <div className="mt-2 space-y-2">
        {section.claims.map((claim) => (
          <ReportClaimRow key={claim.key} claim={claim} />
        ))}
      </div>
    </article>
  );
}

function ReportClaimRow({ claim }: { readonly claim: AgentRunTraceReportClaim }) {
  return (
    <div className="rounded-md bg-[var(--bg-inset)] px-2.5 py-2">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="font-mono text-[10px] font-semibold text-[var(--text-muted)]">
            {claim.key}
          </div>
          <p className="mt-1 text-xs leading-5 text-[var(--text-primary)]">{claim.text}</p>
        </div>
        <span className={claim.material ? materialClass("material") : materialClass("context")}>
          {claim.material ? "material" : "context"}
        </span>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {claim.evidence_ids.map((evidenceId) => (
          <span
            key={`${claim.key}-${evidenceId}`}
            className="rounded-full border border-[var(--success)] bg-[var(--success-subtle)] px-2 py-0.5 font-mono text-[10px] font-medium text-[var(--success)]"
          >
            {evidenceId}
          </span>
        ))}
      </div>
    </div>
  );
}

function sectionCountLabel(count: number): string {
  return count === 1 ? "1 section" : `${count} sections`;
}

function claimCountLabel(count: number): string {
  return count === 1 ? "1 claim" : `${count} claims`;
}

function materialClass(tone: "material" | "context"): string {
  const base = "rounded-full border px-2 py-0.5 text-[10px] font-semibold";
  if (tone === "material") {
    return `${base} border-[var(--success)] bg-[var(--success-subtle)] text-[var(--success)]`;
  }
  return `${base} border-[var(--border-soft)] text-[var(--text-secondary)]`;
}
