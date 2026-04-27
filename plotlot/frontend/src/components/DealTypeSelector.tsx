"use client";

export type DealType = "land_deal" | "wholesale" | "creative_finance" | "hybrid";

interface DealTypeOption {
  id: DealType;
  label: string;
  description: string;
  icon: React.ReactNode;
  metrics: string[];
}

const DEAL_TYPES: DealTypeOption[] = [
  {
    id: "land_deal",
    label: "Land Deal",
    description: "Develop vacant land or rezone for highest & best use",
    icon: (
      <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 21h19.5m-18-18v18m10.5-18v18m6-13.5V21M6.75 6.75h.75m-.75 3h.75m-.75 3h.75m3-6h.75m-.75 3h.75m-.75 3h.75M6.75 21v-3.375c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21M3 3h12m-.75 4.5H21m-3.75 3H21m-3.75 3H21" />
      </svg>
    ),
    metrics: ["Max Units", "Max Offer (RLV)", "Dev Margin %", "Governing Constraint"],
  },
  {
    id: "wholesale",
    label: "Wholesale",
    description: "Find ARV, calculate MAO, and estimate assignment fee",
    icon: (
      <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v12m-3-2.818l.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
    metrics: ["ARV", "MAO (70%)", "Repair Est.", "Assignment Fee"],
  },
  {
    id: "creative_finance",
    label: "Creative Finance",
    description: "SubTo, wrap, or seller financing analysis",
    icon: (
      <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
      </svg>
    ),
    metrics: ["Rate Spread", "Equity Capture", "Monthly Cash Flow", "LTV"],
  },
  {
    id: "hybrid",
    label: "Hybrid",
    description: "Blend strategies for optimal deal structure",
    icon: (
      <svg className="h-6 w-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5" />
      </svg>
    ),
    metrics: ["Blended Rate", "Cash to Close", "Combined CF", "Exit Paths"],
  },
];

const DEAL_TYPE_TEST_IDS: Record<DealType, string> = {
  land_deal: "deal-type-land",
  wholesale: "deal-type-wholesale",
  creative_finance: "deal-type-creative-finance",
  hybrid: "deal-type-hybrid",
};

interface DealTypeSelectorProps {
  onSelect: (dealType: DealType) => void;
  disabled?: boolean;
}

export default function DealTypeSelector({ onSelect, disabled }: DealTypeSelectorProps) {
  return (
    <div className="w-full" data-testid="deal-type-selector">
      <div className="mb-4 text-center">
        <p className="text-sm text-[var(--text-muted)]">What type of deal are you evaluating?</p>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {DEAL_TYPES.map((deal) => (
          <button
            key={deal.id}
            onClick={() => onSelect(deal.id)}
            disabled={disabled}
            aria-label={`${deal.label}: ${deal.description}`}
            data-testid={DEAL_TYPE_TEST_IDS[deal.id]}
            className="group flex min-h-[218px] flex-col items-start gap-2 rounded-[1.5rem] border border-[var(--border-soft)] bg-[var(--bg-surface)] p-2 text-left shadow-[var(--shadow-card)] transition-all duration-700 ease-[cubic-bezier(0.32,0.72,0,1)] hover:-translate-y-1 hover:border-[var(--brand-soft-border)] disabled:opacity-40"
          >
            <div className="flex h-full w-full flex-col rounded-[calc(1.5rem-0.5rem)] border border-white/50 bg-[var(--bg-surface-raised)] p-4 dark:border-white/5">
              <div className="flex items-start justify-between gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-[1rem] bg-amber-50 text-amber-700 transition-colors group-hover:bg-amber-100 dark:bg-amber-950/50 dark:text-amber-400 dark:group-hover:bg-amber-900/50">
                  {deal.icon}
                </div>
              </div>

              <div className="mt-4">
                <h3 className="text-sm font-semibold text-[var(--text-primary)]">{deal.label}</h3>
                <p className="mt-1 text-[11px] leading-5 text-[var(--text-muted)]">{deal.description}</p>
              </div>

              <div className="mt-auto flex flex-wrap gap-1.5 pt-4">
                {deal.metrics.slice(0, 2).map((m) => (
                  <span key={m} className="rounded-full bg-[var(--bg-primary)] px-2 py-1 text-[10px] text-[var(--text-muted)]">
                    {m}
                  </span>
                ))}
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
