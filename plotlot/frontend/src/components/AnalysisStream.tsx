"use client";

import { PipelineStatus } from "@/lib/api";

const STEP_ORDER = ["connecting", "geocoding", "property", "search", "analysis", "calculation"];

const STEP_LABELS: Record<string, string> = {
  connecting: "Connecting",
  geocoding: "Geocoding",
  property: "Property Record",
  search: "Zoning Search",
  analysis: "AI Analysis",
  calculation: "Max Units Calc",
};

const STEP_DESCRIPTIONS: Record<string, string> = {
  connecting: "Connecting...",
  geocoding: "Locating property...",
  property: "Pulling county records...",
  search: "Searching zoning code...",
  analysis: "Extracting standards...",
  calculation: "Computing max units...",
};

interface AnalysisStreamProps {
  steps: PipelineStatus[];
  error: string | null;
  onWrongProperty?: () => void;
}

export default function AnalysisStream({ steps, error, onWrongProperty }: AnalysisStreamProps) {
  if (steps.length === 0 && !error) return null;

  const stepMap = new Map<string, PipelineStatus>();
  for (const s of steps) {
    stepMap.set(s.step, s);
  }

  const completedCount = STEP_ORDER.filter((k) => stepMap.get(k)?.complete).length;
  const activeIdx = STEP_ORDER.findIndex((k) => { const s = stepMap.get(k); return s && !s.complete; });
  const progressPct = Math.round((completedCount / STEP_ORDER.length) * 100);
  const propertyStep = stepMap.get("property");

  return (
    <div className="py-2">
      {/* Progress bar + step counter */}
      <div className="mb-4">
        <div className="mb-1.5 flex items-center justify-between">
          <span className="text-sm font-semibold text-[var(--text-secondary)]">
            Step {Math.min(completedCount + 1, STEP_ORDER.length)} of {STEP_ORDER.length}
            {activeIdx >= 0 && (
              <span className="ml-1.5 font-normal text-stone-500">
                — {STEP_LABELS[STEP_ORDER[activeIdx]]}
              </span>
            )}
          </span>
          <span className="text-xs font-medium text-amber-600">{progressPct}%</span>
        </div>
        <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--bg-surface-raised)]">
          <div
            className="h-full rounded-full bg-amber-500 transition-all duration-500 ease-out"
            style={{ width: `${progressPct}%` }}
          />
        </div>
        <div className="mt-1 text-xs text-stone-500">
          {completedCount < 2
            ? "~30s remaining"
            : completedCount < 4
              ? "~15s remaining"
              : completedCount < STEP_ORDER.length
                ? "Almost done"
                : "Complete"}
        </div>
      </div>

      {/* Property confirmation card */}
      {propertyStep?.complete && propertyStep.resolved_address && (
        <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50/50 p-3 dark:border-amber-800 dark:bg-amber-950/30">
          <div className="flex items-center gap-2">
            <svg className="h-4 w-4 shrink-0 text-amber-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
              <circle cx="12" cy="10" r="3" />
            </svg>
            <span className="text-sm font-medium text-[var(--text-secondary)]">
              {propertyStep.resolved_address}
            </span>
          </div>
          {(propertyStep.folio || propertyStep.lot_sqft) && (
            <div className="mt-1 pl-6 text-xs text-stone-500">
              {propertyStep.folio && <>Folio: {propertyStep.folio}</>}
              {propertyStep.folio && propertyStep.lot_sqft && <> — </>}
              {propertyStep.lot_sqft && <>{Number(propertyStep.lot_sqft).toLocaleString()} sqft</>}
            </div>
          )}
          {onWrongProperty && (
            <button
              onClick={onWrongProperty}
              className="mt-1.5 pl-6 text-xs text-amber-700 underline-offset-2 hover:underline"
            >
              Not the right property? Try a different address
            </button>
          )}
        </div>
      )}

      <div className="relative space-y-0">
        {STEP_ORDER.map((stepKey, idx) => {
          const step = stepMap.get(stepKey);
          const isActive = step && !step.complete;
          const isComplete = step?.complete;
          const isLast = idx === STEP_ORDER.length - 1;
          const stepNum = idx + 1;

          return (
            <div key={stepKey} className="relative flex items-start gap-3 pb-4">
              {/* Connecting line */}
              {!isLast && (
                <div className="absolute left-[11px] top-6 h-full w-px bg-[var(--border)]" />
              )}

              {/* Circled step number */}
              <div className="relative z-10 flex h-[22px] w-[22px] shrink-0 items-center justify-center">
                {isComplete ? (
                  <div className="flex h-[22px] w-[22px] items-center justify-center rounded-full border border-amber-400 bg-amber-50 text-[10px] font-semibold text-amber-700 dark:border-amber-600 dark:bg-amber-950/30 dark:text-amber-400">
                    <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                ) : isActive ? (
                  <div className="flex h-[22px] w-[22px] items-center justify-center rounded-full border border-amber-400 text-[10px] font-semibold text-amber-600 animate-pulse-dot dark:border-amber-500 dark:text-amber-400">
                    {stepNum}
                  </div>
                ) : (
                  <div className="flex h-[22px] w-[22px] items-center justify-center rounded-full border border-[var(--border)] text-[10px] font-medium text-[var(--text-muted)]">
                    {stepNum}
                  </div>
                )}
              </div>

              {/* Step content */}
              <div className="min-w-0 flex-1 -mt-0.5">
                <span
                  className={`text-sm ${
                    isComplete
                      ? "text-[var(--text-muted)]"
                      : isActive
                        ? "font-medium text-[var(--text-secondary)]"
                        : "text-[var(--text-muted)]"
                  }`}
                >
                  {STEP_LABELS[stepKey] || stepKey}
                </span>
                {isActive && (
                  <p className="mt-0.5 text-xs text-[var(--text-muted)]">
                    {step?.message || STEP_DESCRIPTIONS[stepKey]}
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
      {error && (
        <div className="mt-2 text-sm text-red-600">{error}</div>
      )}
    </div>
  );
}
