"use client";

interface ToolCardDef {
  id: string;
  label: string;
  description: string;
  icon: string;
  action: "analyze" | "generate_doc" | "send_prompt";
  prompt?: string;
  docType?: string;
  requiresReport?: boolean;
}

const TOOL_CARDS: ToolCardDef[] = [
  {
    id: "analyze",
    label: "Analyze Property",
    description: "Enter an address for zoning, density & pro forma",
    icon: "M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z",
    action: "analyze",
  },
  {
    id: "generate_loi",
    label: "Generate LOI",
    description: "Draft a letter of intent for this deal",
    icon: "M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z",
    action: "generate_doc",
    docType: "loi",
    requiresReport: true,
  },
  {
    id: "search_comps",
    label: "Search Comps",
    description: "Find comparable sales in the area",
    icon: "M2.25 18.75a60.07 60.07 0 0115.797 2.101c.727.198 1.453-.342 1.453-1.096V18.75M3.75 4.5v.75A.75.75 0 013 6h-.75m0 0v-.375c0-.621.504-1.125 1.125-1.125H20.25M2.25 6v9m18-10.5v.75c0 .414.336.75.75.75h.75m-1.5-1.5h.375c.621 0 1.125.504 1.125 1.125v9.75c0 .621-.504 1.125-1.125 1.125h-.375m1.5-1.5H21a.75.75 0 00-.75.75v.75m0 0H3.75m0 0h-.375a1.125 1.125 0 01-1.125-1.125V15m1.5 1.5v-.75A.75.75 0 003 15h-.75M15 10.5a3 3 0 11-6 0 3 3 0 016 0zm3 0h.008v.008H18V10.5zm-12 0h.008v.008H6V10.5z",
    action: "send_prompt",
    prompt: "Find comparable sales near this property within a 3-mile radius",
    requiresReport: true,
  },
  {
    id: "run_proforma",
    label: "Run Pro Forma",
    description: "Calculate max offer via residual valuation",
    icon: "M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z",
    action: "send_prompt",
    prompt: "Run a detailed pro forma analysis on this property",
    requiresReport: true,
  },
  {
    id: "search_properties",
    label: "Search Properties",
    description: "Find vacant lots or properties by criteria",
    icon: "M9 6.75V15m6-6v8.25m.503 3.498l4.875-2.437c.381-.19.622-.58.622-1.006V4.82c0-.836-.88-1.38-1.628-1.006l-3.869 1.934c-.317.159-.69.159-1.006 0L9.503 3.252a1.125 1.125 0 00-1.006 0L3.622 5.689C3.24 5.88 3 6.27 3 6.695V19.18c0 .836.88 1.38 1.628 1.006l3.869-1.934c.317-.159.69-.159 1.006 0l4.994 2.497c.317.158.69.158 1.006 0z",
    action: "send_prompt",
    prompt: "Find vacant lots in Miami-Dade County",
  },
];

interface ToolCardsProps {
  onAnalyze: () => void;
  onGenerateDoc: (docType: string) => void;
  onSendPrompt: (prompt: string) => void;
  disabled?: boolean;
  hasReport?: boolean;
}

export default function ToolCards({
  onAnalyze,
  onGenerateDoc,
  onSendPrompt,
  disabled = false,
  hasReport = false,
}: ToolCardsProps) {
  const handleClick = (card: ToolCardDef) => {
    if (card.action === "analyze") {
      onAnalyze();
    } else if (card.action === "generate_doc" && card.docType) {
      onGenerateDoc(card.docType);
    } else if (card.action === "send_prompt" && card.prompt) {
      onSendPrompt(card.prompt);
    }
  };

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
      {TOOL_CARDS.map((card) => {
        const isDisabled = disabled || (card.requiresReport && !hasReport);

        return (
          <button
            key={card.id}
            onClick={() => handleClick(card)}
            disabled={isDisabled}
            className="group flex flex-col items-start gap-1.5 rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] p-3 text-left transition-all hover:border-amber-300 hover:bg-amber-50/30 hover:-translate-y-0.5 active:scale-[0.98] disabled:opacity-40 disabled:hover:translate-y-0 disabled:hover:border-[var(--border)] disabled:hover:bg-[var(--bg-surface)] dark:hover:bg-amber-950/20 sm:p-3.5"
          >
            <svg
              className="h-4 w-4 text-amber-600 transition-colors group-hover:text-amber-500 group-disabled:text-[var(--text-muted)]"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
              strokeWidth={1.5}
            >
              <path strokeLinecap="round" strokeLinejoin="round" d={card.icon} />
            </svg>
            <div>
              <span className="text-xs font-medium text-[var(--text-secondary)]">
                {card.label}
              </span>
              <p className="mt-0.5 text-[10px] leading-tight text-[var(--text-muted)]">
                {card.description}
              </p>
            </div>
            {card.requiresReport && !hasReport && (
              <span className="text-[9px] text-amber-600/70">
                Analyze a property first
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
