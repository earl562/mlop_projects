"use client";

import { motion, AnimatePresence } from "framer-motion";
import { PipelineStatus, ThinkingEvent } from "@/lib/api";
import ThinkingIndicator from "@/components/ThinkingIndicator";
import { AnalysisStreamSkeleton } from "@/components/ReportSkeleton";
import { springGentle } from "@/lib/motion";

const STEP_ORDER = ["connecting", "geocoding", "property", "search", "analysis", "calculation", "comps", "proforma"];

const STEP_LABELS: Record<string, string> = {
  connecting: "Connecting",
  geocoding: "Geocoding",
  property: "Property Record",
  search: "Zoning Search",
  analysis: "AI Analysis",
  calculation: "Max Units Calc",
  comps: "Comparable Sales",
  proforma: "Land Pro Forma",
};

const STEP_DESCRIPTIONS: Record<string, string> = {
  connecting: "Establishing connection to PlotLot servers...",
  geocoding: "Resolving address to precise coordinates via Geocodio...",
  property: "Querying county property appraiser records via ArcGIS...",
  search: "Searching zoning ordinance database (hybrid vector + keyword)...",
  analysis: "AI is reading zoning code and extracting dimensional standards...",
  calculation: "Running 4-constraint density calculator (density, lot area, FAR, envelope)...",
  comps: "Discovering comparable sales within 3-mile radius via ArcGIS Hub...",
  proforma: "Computing residual land valuation (GDV - costs - margin = max offer)...",
};

// Narrative messages shown after each step completes
const STEP_NARRATIVES: Record<string, (step: PipelineStatus) => string | null> = {
  geocoding: (s) => s.resolved_address ? `Found property in ${s.resolved_address.split(",").slice(-2, -1)[0]?.trim() || "the target area"}` : null,
  property: (s) => s.folio ? `Retrieved record: Folio ${s.folio}${s.lot_sqft ? `, ${Number(s.lot_sqft).toLocaleString()} sqft` : ""}` : "Property record retrieved",
  search: () => "Found relevant zoning ordinance sections",
  analysis: () => "Extracted numeric dimensional standards",
  calculation: () => "Determined maximum allowable units",
  comps: () => "Comparable sales analysis complete",
  proforma: () => "Pro forma calculated — max offer price determined",
};

interface AnalysisStreamProps {
  steps: PipelineStatus[];
  error: string | null;
  onWrongProperty?: () => void;
  thinkingEvents?: ThinkingEvent[];
}

export default function AnalysisStream({ steps, error, onWrongProperty, thinkingEvents = [] }: AnalysisStreamProps) {
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
    <div
      className="py-2"
      role="status"
      aria-live="polite"
      aria-label="Analysis progress"
      data-testid="pipeline-stepper"
    >
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
        <div
          className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--bg-surface-raised)]"
          role="progressbar"
          aria-valuenow={progressPct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={`Analysis ${progressPct}% complete`}
        >
          <motion.div
            className="h-full rounded-full bg-amber-500"
            animate={{ width: `${progressPct}%` }}
            transition={{ type: "spring", stiffness: 60, damping: 15 }}
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

      {/* Property confirmation card — slides in from bottom */}
      <AnimatePresence>
        {propertyStep?.complete && propertyStep.resolved_address && (
          <motion.div
            key="property-card"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={springGentle}
            className="mb-3 rounded-lg border border-amber-200 bg-amber-50/50 p-3 dark:border-amber-800 dark:bg-amber-950/30"
          >
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
          </motion.div>
        )}
      </AnimatePresence>

      {/* Inline error banner — appears at top of steps on pipeline failure */}
      <AnimatePresence>
        {error && (
          <motion.div
            key="pipeline-error"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={springGentle}
            className="mb-3 rounded-lg border border-red-200 bg-red-50/70 px-3 py-2.5 dark:border-red-800 dark:bg-red-950/30"
          >
            <div className="flex items-start gap-2">
              <svg className="mt-0.5 h-4 w-4 shrink-0 text-red-500" viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z" clipRule="evenodd" />
              </svg>
              <span className="text-sm text-red-700 dark:text-red-400">{error}</span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <div className="relative space-y-0">
        {STEP_ORDER.map((stepKey, idx) => {
          const step = stepMap.get(stepKey);
          const isActive = step && !step.complete;
          const isComplete = step?.complete;
          const isLast = idx === STEP_ORDER.length - 1;
          const stepNum = idx + 1;
          const narrative = isComplete && step && STEP_NARRATIVES[stepKey] ? STEP_NARRATIVES[stepKey]!(step) : null;
          const currentStepTestId = isActive ? "pipeline-step-current" : undefined;

          return (
            <div
              key={stepKey}
              className="relative flex items-start gap-3 pb-4"
              data-testid={`pipeline-step-${stepKey}`}
              {...(currentStepTestId ? { "data-current-step": "true" } : {})}
            >
              {/* Connecting line */}
              {!isLast && (
                <div className="absolute left-[11px] top-6 h-full w-px bg-[var(--border)]" />
              )}

              {/* Step icon with spring scale on state change */}
              <div className="relative z-10 flex h-[22px] w-[22px] shrink-0 items-center justify-center">
                <AnimatePresence mode="wait">
                  {isComplete ? (
                    <motion.div
                      key="complete"
                      initial={{ scale: 0.6, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      transition={springGentle}
                      className="flex h-[22px] w-[22px] items-center justify-center rounded-full border border-amber-400 bg-amber-50 text-[10px] font-semibold text-amber-700 dark:border-amber-600 dark:bg-amber-950/30 dark:text-amber-400"
                    >
                      <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    </motion.div>
                  ) : isActive ? (
                    <motion.div
                      key="active"
                      initial={{ scale: 0.8, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      transition={springGentle}
                      className="flex h-[22px] w-[22px] items-center justify-center rounded-full border border-amber-400 text-[10px] font-semibold text-amber-600 animate-pulse-dot dark:border-amber-500 dark:text-amber-400"
                    >
                      {stepNum}
                    </motion.div>
                  ) : (
                    <motion.div
                      key="pending"
                      initial={{ scale: 0.8, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      transition={springGentle}
                      className="flex h-[22px] w-[22px] items-center justify-center rounded-full border border-[var(--border)] text-[10px] font-medium text-[var(--text-muted)]"
                    >
                      {stepNum}
                    </motion.div>
                  )}
                </AnimatePresence>
              </div>

              {/* Step content */}
              <div className="min-w-0 flex-1 -mt-0.5">
                <span
                  data-testid={currentStepTestId}
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
                <AnimatePresence>
                  {narrative && (
                    <motion.p
                      key={stepKey + "-narrative"}
                      initial={{ opacity: 0, y: 4 }}
                      animate={{ opacity: 1, y: 0 }}
                      exit={{ opacity: 0 }}
                      transition={springGentle}
                      className="mt-0.5 text-xs text-emerald-600 dark:text-emerald-500"
                    >
                      {narrative}
                    </motion.p>
                  )}
                </AnimatePresence>
              </div>
            </div>
          );
        })}
      </div>

      {/* Thinking transparency */}
      {thinkingEvents.length > 0 && (
        <ThinkingIndicator events={thinkingEvents} />
      )}
    </div>
  );
}
