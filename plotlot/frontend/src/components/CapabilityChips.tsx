"use client";

import type { AppMode } from "@/components/ModeToggle";

interface ChipDef {
  label: string;
  prompt: string;
}

const LOOKUP_CHIPS: ChipDef[] = [
  { label: "Miramar, FL", prompt: "6700 Miramar Pkwy, Miramar, FL 33023" },
  { label: "Miami Gardens, FL", prompt: "18901 NW 27th Ave, Miami Gardens, FL 33056" },
  { label: "Boca Raton, FL", prompt: "123 E Palmetto Park Rd, Boca Raton, FL 33432" },
];

const AGENT_CHIPS: ChipDef[] = [
  { label: "Analyze Property", prompt: "Analyze 18901 NW 27th Ave, Miami Gardens, FL 33056" },
  { label: "Generate Documents", prompt: "Generate an LOI for this property" },
  { label: "Search Comps", prompt: "Find comparable sales near 123 Main St, Miami, FL" },
  { label: "Pro Forma", prompt: "Run a pro forma analysis on this property" },
  { label: "Search Properties", prompt: "Find vacant lots in Miami-Dade County" },
];

interface CapabilityChipsProps {
  mode: AppMode;
  onSelect: (prompt: string) => void;
  disabled?: boolean;
}

export default function CapabilityChips({ mode, onSelect, disabled }: CapabilityChipsProps) {
  const chips = mode === "lookup" ? LOOKUP_CHIPS : AGENT_CHIPS;

  return (
    <div className="flex flex-wrap justify-center gap-2">
      {chips.map((chip) => (
        <button
          key={chip.label}
          onClick={() => onSelect(chip.prompt)}
          disabled={disabled}
          className="rounded-full border border-[var(--border)] bg-[var(--bg-surface)] px-4 py-2 text-xs transition-all hover:border-[var(--border-hover)] hover:text-[var(--text-secondary)] hover:-translate-y-0.5 active:scale-[0.98] disabled:opacity-40"
          style={{ color: "var(--text-muted)" }}
        >
          {chip.label}
        </button>
      ))}
    </div>
  );
}
