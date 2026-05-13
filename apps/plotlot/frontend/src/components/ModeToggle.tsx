"use client";

export type AppMode = "lookup" | "agent";

interface ModeToggleProps {
  mode: AppMode;
  onChange: (mode: AppMode) => void;
}

export default function ModeToggle({ mode, onChange }: ModeToggleProps) {
  return (
    <div className="flex shrink-0 items-center gap-1 rounded-full border border-[var(--border)] bg-[var(--bg-inset)] p-1" data-mode-toggle>
      <button
        type="button"
        onClick={() => onChange("lookup")}
        className={`rounded-full px-4 py-1.5 text-sm font-medium transition-all ${
          mode === "lookup"
            ? "bg-[var(--text-primary)] text-[var(--bg-primary)]"
            : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
        }`}
      >
        Lookup
      </button>
      <button
        type="button"
        onClick={() => onChange("agent")}
        className={`rounded-full px-4 py-1.5 text-sm font-medium transition-all ${
          mode === "agent"
            ? "bg-[var(--text-primary)] text-[var(--bg-primary)]"
            : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
        }`}
      >
        Agent
      </button>
    </div>
  );
}
