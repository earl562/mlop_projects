"use client";

export type AppMode = "lookup" | "agent";

interface ModeToggleProps {
  mode: AppMode;
  onChange: (mode: AppMode) => void;
}

export default function ModeToggle({ mode, onChange }: ModeToggleProps) {
  return (
    <div className="flex shrink-0 items-center gap-0.5 rounded-full border border-[var(--border)] bg-[var(--bg-inset)] p-0.5">
      <button
        type="button"
        aria-pressed={mode === "lookup"}
        onClick={() => onChange("lookup")}
        className={`rounded-full px-2 py-1 text-[10px] font-medium transition-all focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand)] sm:px-3 sm:text-[11px] ${
          mode === "lookup"
            ? "bg-[var(--text-primary)] text-[var(--bg-primary)]"
            : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
        }`}
      >
        Lookup
      </button>
      <button
        type="button"
        aria-pressed={mode === "agent"}
        onClick={() => onChange("agent")}
        className={`rounded-full px-2 py-1 text-[10px] font-medium transition-all focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand)] sm:px-3 sm:text-[11px] ${
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
