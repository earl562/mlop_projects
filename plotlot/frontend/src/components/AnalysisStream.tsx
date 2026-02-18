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
    <div className="w-full rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
      <h3 className="mb-4 text-sm font-semibold uppercase tracking-wider text-zinc-400">
        Pipeline Progress
      </h3>
      <div className="space-y-3">
        {STEP_ORDER.map((stepKey) => {
          const step = stepMap.get(stepKey);
          const isActive = step && !step.complete;
          const isComplete = step?.complete;
          const isPending = !step;

          return (
            <div key={stepKey} className="flex items-center gap-3">
              <div className="flex h-6 w-6 items-center justify-center">
                {isComplete ? (
                  <svg className="h-5 w-5 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                ) : isActive ? (
                  <svg className="h-5 w-5 animate-spin text-emerald-400" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                ) : (
                  <div className="h-2.5 w-2.5 rounded-full bg-zinc-700" />
                )}
              </div>
              <div className="flex-1">
                <div className={`text-sm font-medium ${isComplete ? "text-zinc-200" : isActive ? "text-emerald-400" : "text-zinc-600"}`}>
                  {STEP_LABELS[stepKey] || stepKey}
                </div>
                {step && (
                  <div className="text-xs text-zinc-500">{step.message}</div>
                )}
              </div>
            </div>
          );
        })}
      </div>
      {error && (
        <div className="mt-4 rounded-lg border border-red-800/50 bg-red-950/30 p-3 text-sm text-red-400">
          {error}
        </div>
      )}
    </div>
  );
}
