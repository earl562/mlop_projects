import { listMcpTools, type McpToolContract, type ToolRiskClass } from "@/lib/api";

export const dynamic = "force-dynamic";

const RISK_ORDER: ToolRiskClass[] = [
  "read_only",
  "expensive_read",
  "write_internal",
  "write_external",
  "execution",
];

const RISK_COPY: Record<ToolRiskClass, { label: string; tone: string; description: string }> = {
  read_only: {
    label: "Read only",
    tone: "bg-emerald-50 text-emerald-800 border-emerald-100",
    description: "Safe lookup and inspection tools.",
  },
  expensive_read: {
    label: "Live read",
    tone: "bg-amber-50 text-amber-900 border-amber-100",
    description: "Network-backed tools that need budget or approval.",
  },
  write_internal: {
    label: "Internal draft",
    tone: "bg-sky-50 text-sky-900 border-sky-100",
    description: "Creates PlotLot-owned drafts or artifacts only.",
  },
  write_external: {
    label: "External write",
    tone: "bg-rose-50 text-rose-900 border-rose-100",
    description: "Approval-gated writes to connected workspace systems.",
  },
  execution: {
    label: "Execution",
    tone: "bg-stone-100 text-stone-900 border-stone-200",
    description: "Sandboxed execution tools.",
  },
};

function formatName(name: string): string {
  return name
    .split("_")
    .map((part) => part.slice(0, 1).toUpperCase() + part.slice(1))
    .join(" ");
}

function requiredArgs(tool: McpToolContract): string[] {
  const required = tool.input_schema.required;
  return Array.isArray(required) ? required.map(String) : [];
}

function groupTools(tools: McpToolContract[]): Map<ToolRiskClass, McpToolContract[]> {
  const grouped = new Map<ToolRiskClass, McpToolContract[]>();
  for (const risk of RISK_ORDER) grouped.set(risk, []);
  for (const tool of tools) grouped.get(tool.risk_class)?.push(tool);
  for (const [, group] of grouped) group.sort((a, b) => a.name.localeCompare(b.name));
  return grouped;
}

export default async function ConnectorsPage() {
  let tools: McpToolContract[] = [];
  let error: string | null = null;

  try {
    tools = await listMcpTools();
  } catch (err) {
    error = err instanceof Error ? err.message : "Unable to load MCP tools";
  }

  const grouped = groupTools(tools);
  const connectedCount = tools.length;
  const gatedCount = tools.filter((tool) =>
    ["expensive_read", "write_external", "execution"].includes(tool.risk_class),
  ).length;
  const internalDraftCount = tools.filter((tool) => tool.risk_class === "write_internal").length;

  return (
    <main
      className="min-h-full overflow-hidden bg-[var(--bg-primary)] px-4 py-6 sm:px-6 lg:px-10"
      data-testid="connectors-page"
    >
      <section className="relative mx-auto max-w-7xl">
        <h1 className="sr-only">Connectors</h1>
        <div className="pointer-events-none absolute -right-24 -top-24 h-80 w-80 rounded-full bg-[radial-gradient(circle,rgba(180,83,9,0.16),transparent_68%)]" />
        <div className="pointer-events-none absolute -left-20 top-56 h-72 w-72 rounded-full bg-[radial-gradient(circle,rgba(4,120,87,0.10),transparent_68%)]" />

        <div className="relative overflow-hidden rounded-[2rem] border border-[var(--border-soft)] bg-[var(--bg-surface)] p-6 shadow-[var(--shadow-panel)] sm:p-8">
          <div className="grid gap-8 lg:grid-cols-[1.15fr_0.85fr] lg:items-end">
            <div>
              <p className="mb-3 text-xs font-semibold uppercase tracking-[0.24em] text-[var(--brand)]">
                MCP connector plane
              </p>
              <h1 className="font-display text-4xl leading-[0.95] tracking-tight text-[var(--text-primary)] sm:text-6xl">
                Connected tools, visible policy.
              </h1>
              <p className="mt-5 max-w-2xl text-base leading-7 text-[var(--text-secondary)]">
                PlotLot now exposes the same governed tool contracts through REST and the MCP-like
                adapter. Read tools can run directly; live reads and external writes stay behind
                explicit budget and approval gates.
              </p>
            </div>

            <div className="grid grid-cols-3 gap-3">
              <MetricCard label="Connected" value={connectedCount} />
              <MetricCard label="Gated" value={gatedCount} />
              <MetricCard label="Draft tools" value={internalDraftCount} />
            </div>
          </div>

          {error ? (
            <div
              className="mt-8 rounded-2xl border border-[var(--danger)]/20 bg-[var(--danger-subtle)] p-5 text-sm text-[var(--text-primary)]"
              data-testid="mcp-tools-error"
            >
              <p className="font-semibold">MCP tool surface is not reachable yet.</p>
              <p className="mt-1 text-[var(--text-secondary)]">{error}</p>
            </div>
          ) : (
            <div className="mt-8 grid gap-4 lg:grid-cols-4" data-testid="mcp-tools-summary">
              {RISK_ORDER.map((risk) => {
                const count = grouped.get(risk)?.length ?? 0;
                const copy = RISK_COPY[risk];
                return (
                  <div
                    key={risk}
                    className="rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-inset)]/45 p-4"
                  >
                    <div className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold ${copy.tone}`}>
                      {copy.label}
                    </div>
                    <p className="mt-4 text-3xl font-semibold text-[var(--text-primary)]">{count}</p>
                    <p className="mt-1 text-sm leading-5 text-[var(--text-secondary)]">{copy.description}</p>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <section className="relative mt-6 grid gap-5" data-testid="mcp-tools-list">
          {RISK_ORDER.map((risk) => {
            const group = grouped.get(risk) ?? [];
            if (!group.length) return null;
            const copy = RISK_COPY[risk];

            return (
              <div
                key={risk}
                className="rounded-[1.5rem] border border-[var(--border-soft)] bg-[var(--bg-surface)] p-5 shadow-[var(--shadow-card)]"
              >
                <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold ${copy.tone}`}>
                      {copy.label}
                    </div>
                    <p className="mt-2 text-sm text-[var(--text-secondary)]">{copy.description}</p>
                  </div>
                  <p className="text-sm font-medium text-[var(--text-muted)]">
                    {group.length} {group.length === 1 ? "tool" : "tools"}
                  </p>
                </div>

                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                  {group.map((tool) => {
                    const required = requiredArgs(tool);
                    return (
                      <article
                        key={tool.name}
                        className="group rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-primary)]/65 p-4 transition duration-200 hover:-translate-y-0.5 hover:border-[var(--border-hover)]"
                        data-testid={`mcp-tool-${tool.name}`}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div>
                            <h2 className="text-base font-semibold text-[var(--text-primary)]">
                              {formatName(tool.name)}
                            </h2>
                            <code className="mt-1 block text-xs text-[var(--brand)]">{tool.name}</code>
                          </div>
                          <span className="rounded-full bg-[var(--bg-surface)] px-2.5 py-1 text-[11px] font-semibold text-[var(--text-secondary)]">
                            {tool.timeout_seconds}s
                          </span>
                        </div>
                        <p className="mt-3 min-h-12 text-sm leading-6 text-[var(--text-secondary)]">
                          {tool.description}
                        </p>
                        <div className="mt-4 flex flex-wrap gap-2">
                          {required.length ? (
                            required.map((arg) => (
                              <span
                                key={arg}
                                className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-surface)] px-2.5 py-1 text-xs text-[var(--text-secondary)]"
                              >
                                {arg}
                              </span>
                            ))
                          ) : (
                            <span className="rounded-full border border-[var(--border-soft)] bg-[var(--bg-surface)] px-2.5 py-1 text-xs text-[var(--text-muted)]">
                              optional args
                            </span>
                          )}
                        </div>
                      </article>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </section>
      </section>
    </main>
  );
}

function MetricCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-primary)]/70 p-4 text-center">
      <p className="text-3xl font-semibold text-[var(--text-primary)]">{value}</p>
      <p className="mt-1 text-xs font-semibold uppercase tracking-[0.16em] text-[var(--text-muted)]">
        {label}
      </p>
    </div>
  );
}
