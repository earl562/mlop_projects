import Link from "next/link";

export default async function ProjectPage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return (
    <main className="min-h-[100dvh] px-6 py-8">
      <section className="mx-auto grid min-h-[460px] w-full max-w-4xl content-center gap-5 rounded-lg border border-[var(--border)] bg-[var(--bg-surface)] p-8 shadow-[var(--shadow-card)]">
        <p className="rounded-full border border-[var(--border-soft)] px-3 py-1 text-[11px] font-medium uppercase tracking-[0.14em] text-[var(--text-muted)]">
          Project Workspace
        </p>
        <h1 className="text-2xl font-semibold text-[var(--text-primary)]">Project</h1>
        <p className="max-w-2xl text-sm leading-relaxed text-[var(--text-secondary)]">
          This project has no visible sites or analyses.
        </p>
        <p className="rounded-lg border border-[var(--border-soft)] bg-[var(--bg-surface-raised)] px-4 py-2.5 text-xs font-mono text-[var(--text-muted)]">
          projectId: {projectId}
        </p>
        <Link
          href="/projects"
          className="inline-flex w-fit items-center justify-center rounded-lg border border-[var(--border)] bg-[var(--bg-surface)] px-4 py-2 text-sm font-semibold text-[var(--text-secondary)] transition-colors hover:bg-[var(--bg-surface-raised)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand)]"
        >
          Back to projects
        </Link>
      </section>
    </main>
  );
}
