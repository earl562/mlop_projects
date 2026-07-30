import HarnessRunDetail from "@/components/HarnessRunDetail";

function looksLikeHarnessRunId(value: string) {
  return /^run_[a-z0-9_]+$/i.test(value);
}

export default async function AnalysisPage({
  params,
}: {
  params: Promise<{ projectId: string; siteId: string; analysisId: string }>;
}) {
  const { projectId, siteId, analysisId } = await params;

  if (!looksLikeHarnessRunId(analysisId)) {
    return (
      <main className="mx-auto max-w-5xl px-6 py-8">
        <section className="rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)] p-6 shadow-[var(--shadow-card)]">
          <span className="section-pill">Analysis</span>
          <h1 className="mt-3 text-2xl font-semibold text-[var(--text-primary)]">Analysis workspace</h1>
          <p className="mt-2 text-sm text-[var(--text-secondary)]">
            Analysis <span className="font-mono text-xs text-[var(--text-primary)]">{analysisId}</span> is a workspace
            analysis record. Persisted harness run inspection uses a harness run id once a shared run has been linked.
          </p>
          <dl className="mt-5 grid gap-4 md:grid-cols-3">
            <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface-raised)] p-4">
              <dt className="text-xs uppercase tracking-[0.08em] text-[var(--text-muted)]">Project</dt>
              <dd className="mt-2 font-mono text-xs text-[var(--text-primary)]">{projectId}</dd>
            </div>
            <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface-raised)] p-4">
              <dt className="text-xs uppercase tracking-[0.08em] text-[var(--text-muted)]">Site</dt>
              <dd className="mt-2 font-mono text-xs text-[var(--text-primary)]">{siteId}</dd>
            </div>
            <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface-raised)] p-4">
              <dt className="text-xs uppercase tracking-[0.08em] text-[var(--text-muted)]">Analysis record</dt>
              <dd className="mt-2 font-mono text-xs text-[var(--text-primary)]">{analysisId}</dd>
            </div>
          </dl>
        </section>
      </main>
    );
  }

  return (
    <HarnessRunDetail
      runId={analysisId}
      projectId={projectId}
      siteId={siteId}
    />
  );
}
