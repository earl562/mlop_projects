"use client";

import { PipelineStatus } from "@/lib/api";

const STEP_ORDER = ["geocoding", "property", "search", "analysis", "calculation"];

const STEP_LABELS: Record<string, string> = {
  geocoding: "Geocoding",
  property: "Property Record",
  search: "Zoning Search",
  analysis: "AI Analysis",
  calculation: "Density Calc",
};

interface AnalysisStreamProps {
  steps: PipelineStatus[];
  error: string | null;
}

export default function AnalysisStream({ steps, error }: AnalysisStreamProps) {
  if (steps.length === 0 && !error) return null;

  const stepMap = new Map<string, PipelineStatus>();
  for (const s of steps) {
    stepMap.set(s.step, s);
  }

  return (
    <div className="py-2">
      <div className="relative space-y-0">
        {STEP_ORDER.map((stepKey, idx) => {
          const step = stepMap.get(stepKey);
          const isActive = step && !step.complete;
          const isComplete = step?.complete;
          const isLast = idx === STEP_ORDER.length - 1;

          return (
            <div key={stepKey} className="relative flex items-start gap-3 pb-4">
              {/* Connecting line */}
              {!isLast && (
                <div className="absolute left-[9px] top-5 h-full w-px bg-stone-200" />
              )}

              {/* Step indicator */}
              <div className="relative z-10 flex h-[18px] w-[18px] shrink-0 items-center justify-center">
                {isComplete ? (
                  <svg className="h-[18px] w-[18px] text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                ) : isActive ? (
                  <div className="h-2.5 w-2.5 rounded-full bg-amber-500 animate-pulse-dot" />
                ) : (
                  <div className="h-2 w-2 rounded-full bg-stone-300" />
                )}
              </div>

              {/* Step content */}
              <div className="min-w-0 flex-1 -mt-0.5">
                <span
                  className={`text-sm ${
                    isComplete
                      ? "text-stone-400"
                      : isActive
                        ? "font-medium text-stone-700"
                        : "text-stone-400"
                  }`}
                >
                  {STEP_LABELS[stepKey] || stepKey}
                </span>
                {step?.message && isActive && (
                  <span className="ml-2 text-xs text-stone-400">{step.message}</span>
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
