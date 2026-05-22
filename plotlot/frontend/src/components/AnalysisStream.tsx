"use client";

import { useEffect, useReducer, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { PipelineStatus, ThinkingEvent } from "@/lib/api";
import ThinkingIndicator from "@/components/ThinkingIndicator";
import { springGentle } from "@/lib/motion";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STEP_ORDER = [
  "connecting",
  "geocoding",
  "property",
  "search",
  "analysis",
  "calculation",
  "comps",
  "proforma",
];

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

// Static narratives shown when a step has no dynamic message from the backend
const STEP_FALLBACK_NARRATIVES: Record<string, string> = {
  connecting: "Connected",
  search: "Found relevant zoning ordinance sections",
  analysis: "Extracted numeric dimensional standards",
  calculation: "Determined maximum allowable units",
  comps: "Comparable sales analysis complete",
  proforma: "Pro forma calculated — max offer price determined",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatElapsed(ms: number): string {
  return `${(ms / 1000).toFixed(1)}s`;
}

// ---------------------------------------------------------------------------
// StepSnippet — inline result shown after each step completes
// ---------------------------------------------------------------------------

function StepSnippet({
  stepKey,
  step,
  onWrongProperty,
}: {
  stepKey: string;
  step: PipelineStatus;
  onWrongProperty?: () => void;
}) {
  if (!step.complete) return null;

  // Geocoding: show county extracted from resolved_address
  if (stepKey === "geocoding" && step.resolved_address) {
    const county = step.resolved_address.split(",").slice(-2, -1)[0]?.trim();
    return (
      <p className="mt-1 text-xs text-emerald-600 dark:text-emerald-500">
        Located in {county || "target area"}
      </p>
    );
  }

  // Property: rich snippet with folio, lot size, address, wrong-property CTA
  if (stepKey === "property") {
    const parts: string[] = [];
    if (step.folio) parts.push(`Folio ${step.folio}`);
    if (step.lot_sqft) parts.push(`${Number(step.lot_sqft).toLocaleString()} sqft`);

    return (
      <div className="mt-1 space-y-0.5">
        {parts.length > 0 && (
          <p className="text-xs text-emerald-600 dark:text-emerald-500">
            {parts.join(" · ")}
          </p>
        )}
        {step.resolved_address && (
          <p className="text-xs text-[var(--text-muted)]">{step.resolved_address}</p>
        )}
        {onWrongProperty && (
          <button
            onClick={onWrongProperty}
            className="text-[11px] text-amber-600 underline-offset-2 hover:underline dark:text-amber-400"
          >
            Not the right property?
          </button>
        )}
      </div>
    );
  }

  // All other steps: prefer backend message, fall back to static narrative
  const text = step.message || STEP_FALLBACK_NARRATIVES[stepKey];
  if (!text) return null;

  return (
    <p className="mt-1 text-xs text-emerald-600 dark:text-emerald-500">{text}</p>
  );
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface AnalysisStreamProps {
  steps: PipelineStatus[];
  error: string | null;
  onWrongProperty?: () => void;
  thinkingEvents?: ThinkingEvent[];
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function AnalysisStream({
  steps,
  error,
  onWrongProperty,
  thinkingEvents = [],
}: AnalysisStreamProps) {
  // All hooks must be declared before any early return.

  // Force a re-render every 100ms while a step is active so the live
  // elapsed counter ticks. useReducer avoids an unused-state-value warning.
  const [, forceUpdate] = useReducer((x: number) => x + 1, 0);

  // Per-step wall-clock timing. Mutated in the effect below; read at render
  // time via Date.now() so each re-render gets the latest elapsed value.
  const timingRef = useRef<Map<string, { startMs: number; endMs?: number }>>(
    new Map()
  );

  // Track when steps start and complete.
  useEffect(() => {
    const now = Date.now();
    for (const step of steps) {
      const existing = timingRef.current.get(step.step);
      if (!existing) {
        // First time this step appears → record start
        timingRef.current.set(step.step, { startMs: now });
      } else if (step.complete && !existing.endMs) {
        // Step just flipped to complete → record end
        timingRef.current.set(step.step, { ...existing, endMs: now });
      }
    }
  }, [steps]);

  // Tick interval: runs only while there is an active (started, not complete) step.
  useEffect(() => {
    const hasActive = steps.some((s) => !s.complete);
    if (!hasActive) return;
    const id = setInterval(forceUpdate, 100);
    return () => clearInterval(id);
  }, [steps]);

  // Early return — after all hooks.
  if (steps.length === 0 && !error) return null;

  // ---------------------------------------------------------------------------
  // Derived values (re-computed each render, including every 100ms tick)
  // ---------------------------------------------------------------------------

  const stepMap = new Map<string, PipelineStatus>();
  for (const s of steps) stepMap.set(s.step, s);

  const completedCount = STEP_ORDER.filter((k) => stepMap.get(k)?.complete).length;
  const activeIdx = STEP_ORDER.findIndex((k) => {
    const s = stepMap.get(k);
    return s && !s.complete;
  });
  const progressPct = Math.round((completedCount / STEP_ORDER.length) * 100);
  const allDone = completedCount === STEP_ORDER.length;
  const now = Date.now();

  // Total pipeline duration: first step start → last step end
  let totalElapsedLabel = "";
  if (allDone) {
    let earliest = Infinity;
    let latest = 0;
    timingRef.current.forEach(({ startMs, endMs }) => {
      if (startMs < earliest) earliest = startMs;
      if (endMs && endMs > latest) latest = endMs;
    });
    if (earliest !== Infinity && latest > 0) {
      totalElapsedLabel = `Completed in ${formatElapsed(latest - earliest)}`;
    } else {
      totalElapsedLabel = "Complete";
    }
  }

  // Live elapsed label shown below the progress bar while a step is active
  let progressSubLabel = "";
  if (activeIdx >= 0) {
    const activeTiming = timingRef.current.get(STEP_ORDER[activeIdx]);
    if (activeTiming) {
      const elapsed = now - activeTiming.startMs;
      // Cap display at 30s with a cold-start hint (connecting step can run long)
      if (elapsed > 30_000 && STEP_ORDER[activeIdx] === "connecting") {
        progressSubLabel = "30s+ — server may be warming up";
      } else {
        progressSubLabel = `${formatElapsed(elapsed)} on this step`;
      }
    } else {
      progressSubLabel = "Starting...";
    }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  return (
    <div
      className="py-2"
      role="status"
      aria-live="polite"
      aria-label="Analysis progress"
      data-testid="pipeline-stepper"
    >
      {/* ── Progress bar ─────────────────────────────────────────────────── */}
      <div className="mb-4">
        <div className="mb-1.5 flex items-center justify-between">
          <span className="text-sm font-semibold text-[var(--text-secondary)]">
            {allDone ? (
              "Analysis complete"
            ) : (
              <>
                Step {Math.min(completedCount + 1, STEP_ORDER.length)} of{" "}
                {STEP_ORDER.length}
                {activeIdx >= 0 && (
                  <span className="ml-1.5 font-normal text-stone-500">
                    — {STEP_LABELS[STEP_ORDER[activeIdx]]}
                  </span>
                )}
              </>
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

        {/* Sub-label: live elapsed while running, total time when done */}
        <div className="mt-1 text-xs text-stone-500">
          {allDone ? totalElapsedLabel : progressSubLabel}
        </div>
      </div>

      {/* ── Error banner ─────────────────────────────────────────────────── */}
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
              <svg
                className="mt-0.5 h-4 w-4 shrink-0 text-red-500"
                viewBox="0 0 20 20"
                fill="currentColor"
              >
                <path
                  fillRule="evenodd"
                  d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.28 7.22a.75.75 0 00-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 101.06 1.06L10 11.06l1.72 1.72a.75.75 0 101.06-1.06L11.06 10l1.72-1.72a.75.75 0 00-1.06-1.06L10 8.94 8.28 7.22z"
                  clipRule="evenodd"
                />
              </svg>
              <span className="text-sm text-red-700 dark:text-red-400">{error}</span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Step list ────────────────────────────────────────────────────── */}
      <div className="relative space-y-0">
        {STEP_ORDER.map((stepKey, idx) => {
          const step = stepMap.get(stepKey);
          const isActive = step !== undefined && !step.complete;
          const isComplete = step?.complete === true;
          const isLast = idx === STEP_ORDER.length - 1;
          const stepNum = idx + 1;

          const timing = timingRef.current.get(stepKey);
          const duration =
            timing?.endMs !== undefined ? timing.endMs - timing.startMs : null;
          const liveElapsed =
            isActive && timing ? now - timing.startMs : null;

          return (
            <div
              key={stepKey}
              className="relative flex items-start gap-3 pb-4"
              data-testid={`pipeline-step-${stepKey}`}
              {...(isActive ? { "data-current-step": "true" } : {})}
            >
              {/* Vertical connecting line between steps */}
              {!isLast && (
                <div className="absolute left-[11px] top-6 h-full w-px bg-[var(--border)]" />
              )}

              {/* Step icon — pending / active / complete */}
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
                      <svg
                        className="h-3 w-3"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                        strokeWidth={3}
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          d="M5 13l4 4L19 7"
                        />
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
                {/* Label row with timing badge */}
                <div className="flex items-center gap-2">
                  <span
                    data-testid={isActive ? "pipeline-step-current" : undefined}
                    className={`text-sm ${
                      isComplete
                        ? "text-[var(--text-muted)]"
                        : isActive
                          ? "font-medium text-[var(--text-secondary)]"
                          : "text-[var(--text-muted)]"
                    }`}
                  >
                    {STEP_LABELS[stepKey] ?? stepKey}
                  </span>

                  {/* Duration badge — springs in when step completes */}
                  <AnimatePresence>
                    {isComplete && duration !== null && (
                      <motion.span
                        key={`${stepKey}-duration`}
                        initial={{ opacity: 0, scale: 0.75 }}
                        animate={{ opacity: 1, scale: 1 }}
                        transition={springGentle}
                        className="rounded-full bg-[var(--bg-surface-raised)] px-1.5 py-0.5 text-[10px] tabular-nums text-[var(--text-muted)]"
                      >
                        {formatElapsed(duration)}
                      </motion.span>
                    )}
                  </AnimatePresence>

                  {/* Live elapsed counter on the active step */}
                  {isActive && liveElapsed !== null && (
                    <span className="text-[10px] tabular-nums text-amber-500">
                      {formatElapsed(liveElapsed)}
                    </span>
                  )}
                </div>

                {/* Active step: show description or backend message */}
                {isActive && (
                  <p className="mt-0.5 text-xs text-[var(--text-muted)]">
                    {step?.message || STEP_DESCRIPTIONS[stepKey]}
                  </p>
                )}

                {/* Completed step: inline result snippet */}
                {isComplete && step && (
                  <AnimatePresence>
                    <motion.div
                      key={`${stepKey}-snippet`}
                      initial={{ opacity: 0, y: 3 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={springGentle}
                    >
                      <StepSnippet
                        stepKey={stepKey}
                        step={step}
                        onWrongProperty={
                          stepKey === "property" ? onWrongProperty : undefined
                        }
                      />
                    </motion.div>
                  </AnimatePresence>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* ── AI reasoning (extended thinking events) ──────────────────────── */}
      {thinkingEvents.length > 0 && (
        <ThinkingIndicator events={thinkingEvents} />
      )}
    </div>
  );
}
