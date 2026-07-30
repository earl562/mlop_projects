"use client";

import type { HarnessPipelineStageData } from "@/lib/api";

type Props = {
  stages: readonly HarnessPipelineStageData[];
};

function stageTone(value: string) {
  const normalized = value.toLowerCase();
  if (normalized.includes("complete") || normalized.includes("pass")) return "text-[var(--success)]";
  if (normalized.includes("warning") || normalized.includes("partial")) return "text-[var(--warning)]";
  if (normalized.includes("missing") || normalized.includes("fail")) return "text-[var(--danger)]";
  return "text-[var(--text-secondary)]";
}

export default function HarnessPipelineStageChain({ stages }: Props) {
  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)] p-6 shadow-[var(--shadow-card)]">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">Pipeline trace</h2>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            Shared harness stages for address, zoning, comps, and underwriting.
          </p>
        </div>
        <p className="text-xs uppercase tracking-[0.08em] text-[var(--text-muted)]">{stages.length} stages</p>
      </div>

      <div className="mt-5 grid gap-4 xl:grid-cols-5">
        {stages.map((stage) => (
          <article
            key={stage.key}
            className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface-raised)] p-4"
          >
            <div className="flex items-start justify-between gap-3">
              <h3 className="text-sm font-medium text-[var(--text-primary)]">{stage.title}</h3>
              <p className={`text-xs font-semibold uppercase tracking-[0.08em] ${stageTone(stage.status)}`}>
                {stage.status.replaceAll("_", " ")}
              </p>
            </div>
            <p className="mt-3 text-sm text-[var(--text-secondary)]">{stage.summary}</p>
            <p className="mt-3 text-xs text-[var(--text-muted)]">
              Artifacts: {stage.artifact_keys.join(", ")}
            </p>
          </article>
        ))}
      </div>
    </section>
  );
}
