import Link from "next/link";

export default function ProjectsPage() {
  return (
    <main className="min-h-[100dvh] px-6 py-8">
      <section className="mx-auto grid min-h-[460px] w-full max-w-4xl content-center gap-5 rounded-lg border border-[var(--border)] bg-[var(--bg-surface)] p-8 shadow-[var(--shadow-card)]">
        <p className="rounded-full border border-[var(--border-soft)] px-3 py-1 text-[11px] font-medium uppercase tracking-[0.14em] text-[var(--text-muted)]">
          Workspace
        </p>
        <h1 className="text-2xl font-semibold text-[var(--text-primary)]">Projects</h1>
        <p className="max-w-2xl text-sm leading-relaxed text-[var(--text-secondary)]">
          No projects are attached to this workspace.
        </p>
        <Link
          href="/workspace?mode=lookup"
          className="inline-flex w-fit items-center justify-center rounded-lg bg-[var(--text-primary)] px-4 py-2 text-sm font-semibold text-[var(--bg-primary)] transition-opacity hover:opacity-90 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand)]"
        >
          Start analysis
        </Link>
      </section>
    </main>
  );
}
