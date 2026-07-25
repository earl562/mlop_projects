export interface HarnessLifecycleContextValue {
  readonly enabled: boolean;
  readonly workspaceId: string;
  readonly projectId: string;
  readonly siteId: string;
  readonly analysisId: string;
  readonly analysisName: string;
}

interface Props {
  readonly value: HarnessLifecycleContextValue;
  readonly onChange: (value: HarnessLifecycleContextValue) => void;
}

export function HarnessLifecycleContextFields({ value, onChange }: Props) {
  return (
    <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-surface-raised)] p-4 lg:col-span-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">Analysis lifecycle</h2>
          <p className="mt-1 text-sm text-[var(--text-secondary)]">
            Optionally create or reuse a durable analysis record before launching the shared harness run.
          </p>
        </div>
        <button
          type="button"
          onClick={() => onChange({ ...value, enabled: !value.enabled })}
          className={`rounded-xl border px-3 py-2 text-sm font-medium transition ${
            value.enabled
              ? "border-[var(--brand)] bg-[var(--brand-subtle)] text-[var(--brand)]"
              : "border-[var(--border)] bg-[var(--bg-surface)] text-[var(--text-secondary)]"
          }`}
        >
          {value.enabled ? "Lifecycle on" : "Lifecycle off"}
        </button>
      </div>

      {value.enabled ? (
        <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          <label className="flex flex-col gap-2 text-sm text-[var(--text-secondary)]">
            Workspace ID
            <input
              className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] px-4 py-3 text-[var(--text-primary)]"
              value={value.workspaceId}
              onChange={(event) => onChange({ ...value, workspaceId: event.target.value })}
            />
          </label>
          <label className="flex flex-col gap-2 text-sm text-[var(--text-secondary)]">
            Project ID
            <input
              className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] px-4 py-3 text-[var(--text-primary)]"
              value={value.projectId}
              onChange={(event) => onChange({ ...value, projectId: event.target.value })}
            />
          </label>
          <label className="flex flex-col gap-2 text-sm text-[var(--text-secondary)]">
            Site ID
            <input
              className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] px-4 py-3 text-[var(--text-primary)]"
              value={value.siteId}
              onChange={(event) => onChange({ ...value, siteId: event.target.value })}
            />
          </label>
          <label className="flex flex-col gap-2 text-sm text-[var(--text-secondary)]">
            Existing analysis ID
            <input
              className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] px-4 py-3 text-[var(--text-primary)]"
              value={value.analysisId}
              onChange={(event) => onChange({ ...value, analysisId: event.target.value })}
            />
          </label>
          <label className="flex flex-col gap-2 text-sm text-[var(--text-secondary)]">
            New analysis name
            <input
              className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] px-4 py-3 text-[var(--text-primary)]"
              value={value.analysisName}
              onChange={(event) => onChange({ ...value, analysisName: event.target.value })}
            />
          </label>
        </div>
      ) : null}
    </section>
  );
}
