"use client";

import { useCallback, useReducer, useRef } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { spring, springGentle, fadeUp, staggerContainer, staggerItem } from "@/lib/motion";
import {
  streamDatacenterAnalysis,
  type SiteScorecardData,
  type DatacenterPipelineSignalEvent,
  type PipelineStatus,
  type AnalysisError,
} from "@/lib/api";
import { SiteScorecard } from "./SiteScorecard";

// ---------------------------------------------------------------------------
// State machine
// ---------------------------------------------------------------------------

type Phase =
  | "idle"
  | "geocoding"
  | "property"
  | "zoning_search"
  | "infrastructure"
  | "scoring"
  | "summary"
  | "done"
  | "error";

interface DCStreamState {
  phase: Phase;
  statusMessage: string;
  signals: DatacenterPipelineSignalEvent[];
  compositeScore: number | null;
  compositeRating: string;
  scorecard: SiteScorecardData | null;
  error: AnalysisError | null;
}

type DCStreamAction =
  | { type: "STATUS"; payload: PipelineStatus }
  | { type: "SIGNAL"; payload: DatacenterPipelineSignalEvent }
  | { type: "DONE"; payload: SiteScorecardData }
  | { type: "ERROR"; payload: AnalysisError }
  | { type: "RESET" };

function reducer(state: DCStreamState, action: DCStreamAction): DCStreamState {
  switch (action.type) {
    case "STATUS":
      return {
        ...state,
        phase: (action.payload.step as Phase) || state.phase,
        statusMessage: action.payload.message || state.statusMessage,
        compositeScore: action.payload.composite_score ?? state.compositeScore,
        compositeRating: action.payload.composite_rating ?? state.compositeRating,
      };
    case "SIGNAL":
      return {
        ...state,
        phase: "infrastructure",
        signals: [...state.signals, action.payload],
      };
    case "DONE":
      return {
        ...state,
        phase: "done",
        scorecard: action.payload,
      };
    case "ERROR":
      return { ...state, phase: "error", error: action.payload };
    case "RESET":
      return initialState;
  }
}

const initialState: DCStreamState = {
  phase: "idle",
  statusMessage: "",
  signals: [],
  compositeScore: null,
  compositeRating: "",
  scorecard: null,
  error: null,
};

// ---------------------------------------------------------------------------
// Pipeline step indicator
// ---------------------------------------------------------------------------

const STEPS = [
  { key: "geocoding", label: "Geocode" },
  { key: "property", label: "Parcel" },
  { key: "zoning_search", label: "Ordinances" },
  { key: "infrastructure", label: "Infrastructure" },
  { key: "scoring", label: "Score" },
  { key: "summary", label: "Summary" },
];

const PHASE_ORDER = ["geocoding", "property", "zoning_search", "infrastructure", "scoring", "summary", "done", "error"];

function StepProgress({ currentPhase }: { currentPhase: Phase }) {
  // On error, show all steps as incomplete (currentIdx = last real step before error)
  const currentIdx = currentPhase === "error" ? -1 : PHASE_ORDER.indexOf(currentPhase);

  return (
    <div className="flex items-center gap-1.5 overflow-x-auto pb-1">
      {STEPS.map((step, i) => {
        const isDone = currentIdx > i;
        const isActive = PHASE_ORDER[currentIdx] === step.key;
        return (
          <div key={step.key} className="flex items-center gap-1.5">
            <div
              className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium whitespace-nowrap transition-colors duration-300 ${
                isDone
                  ? "bg-emerald-500/15 text-emerald-400"
                  : isActive
                    ? "bg-amber-500/15 text-amber-400 ring-1 ring-amber-500/30"
                    : "bg-stone-900 text-stone-600"
              }`}
            >
              {isDone && <span aria-hidden>✓</span>}
              {isActive && (
                <span className="inline-block h-1.5 w-1.5 rounded-full bg-amber-400 animate-pulse" aria-hidden />
              )}
              {step.label}
            </div>
            {i < STEPS.length - 1 && (
              <div className={`h-px w-3 ${isDone || isActive ? "bg-stone-700" : "bg-stone-800"}`} />
            )}
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Live signal card (arrives during streaming)
// ---------------------------------------------------------------------------

const RATING_COLORS: Record<string, string> = {
  Excellent: "text-emerald-400 bg-emerald-500/10",
  Good: "text-amber-400 bg-amber-500/10",
  Fair: "text-yellow-400 bg-yellow-500/10",
  Poor: "text-red-400 bg-red-500/10",
};

const SIGNAL_ICONS: Record<string, string> = {
  power: "⚡",
  power_grid: "⚡",
  fiber: "🌐",
  flood: "🌊",
  flood_zone: "🌊",
  seismic: "🏔",
  zoning: "📋",
};

function LiveSignalCard({ signal, index }: { signal: DatacenterPipelineSignalEvent; index: number }) {
  const icon = SIGNAL_ICONS[signal.signal] ?? "●";
  const ratingClass = RATING_COLORS[signal.rating] ?? "text-stone-400 bg-stone-800";
  const pct = Math.round(signal.score * 100);

  return (
    <motion.div
      variants={staggerItem}
      className="rounded-xl border border-stone-800 bg-stone-900/60 p-3"
    >
      <div className="flex items-center justify-between gap-2 mb-2">
        <div className="flex items-center gap-1.5">
          <span className="text-sm" aria-hidden>{icon}</span>
          <span className="text-sm font-medium text-stone-200">{signal.label}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold tabular-nums text-stone-300">{pct}%</span>
          <span className={`rounded-full px-2 py-0.5 text-xs font-semibold ${ratingClass}`}>
            {signal.rating}
          </span>
        </div>
      </div>

      {/* Score bar */}
      <div className="h-1 w-full overflow-hidden rounded-full bg-stone-800 mb-2">
        <motion.div
          className={`h-full rounded-full ${
            pct >= 85 ? "bg-emerald-500" : pct >= 70 ? "bg-amber-500" : pct >= 50 ? "bg-yellow-500" : "bg-red-500"
          }`}
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ type: "spring", stiffness: 120, damping: 20, delay: index * 0.05 }}
        />
      </div>

      <p className="text-xs text-stone-400 leading-relaxed">{signal.summary}</p>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Address input
// ---------------------------------------------------------------------------

interface AddressInputProps {
  onSubmit: (address: string) => void;
  isLoading: boolean;
}

function AddressInput({ onSubmit, isLoading }: AddressInputProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const val = inputRef.current?.value.trim();
    if (val) onSubmit(val);
  };

  return (
    <motion.form
      {...fadeUp}
      transition={springGentle}
      onSubmit={handleSubmit}
      className="flex gap-2"
    >
      <input
        ref={inputRef}
        type="text"
        placeholder="Enter industrial/commercial site address..."
        disabled={isLoading}
        className="flex-1 rounded-xl border border-stone-700 bg-stone-900 px-4 py-3 text-sm text-stone-100 placeholder-stone-500 focus:border-amber-600 focus:outline-none focus:ring-1 focus:ring-amber-600 disabled:opacity-50"
      />
      <motion.button
        type="submit"
        disabled={isLoading}
        whileHover={{ scale: 1.01, transition: spring }}
        whileTap={{ scale: 0.97 }}
        className="rounded-xl bg-amber-700 px-5 py-3 text-sm font-semibold text-white hover:bg-amber-600 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {isLoading ? "Analyzing…" : "Analyze Site"}
      </motion.button>
    </motion.form>
  );
}

// ---------------------------------------------------------------------------
// Main DataCenterStream component
// ---------------------------------------------------------------------------

export function DataCenterStream() {
  const [state, dispatch] = useReducer(reducer, initialState);
  const isLoading = !["idle", "done", "error"].includes(state.phase);

  const handleAnalyze = useCallback(async (address: string) => {
    dispatch({ type: "RESET" });

    await streamDatacenterAnalysis(
      address,
      (status) => dispatch({ type: "STATUS", payload: status }),
      (signal) => dispatch({ type: "SIGNAL", payload: signal }),
      (scorecard) => dispatch({ type: "DONE", payload: scorecard }),
      (error) => dispatch({ type: "ERROR", payload: error }),
    );
  }, []);

  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-8">
      {/* Page header */}
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={springGentle}
      >
        <div className="flex items-center gap-3 mb-1">
          <span className="text-2xl" aria-hidden>🏭</span>
          <h1 className="text-2xl font-bold text-stone-100">Data Center Site Selection</h1>
        </div>
        <p className="text-sm text-stone-400 ml-11">
          Evaluate industrial sites across 5 infrastructure signals: power grid, fiber, flood zone, seismic risk, and zoning.
        </p>
      </motion.div>

      {/* Address input */}
      <AddressInput onSubmit={handleAnalyze} isLoading={isLoading} />

      {/* Pipeline progress */}
      <AnimatePresence>
        {!["idle"].includes(state.phase) && (
          <motion.div
            key="progress"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={spring}
            className="space-y-3"
          >
            <StepProgress currentPhase={state.phase} />

            {/* Status message */}
            <AnimatePresence mode="wait">
              {state.statusMessage && state.phase !== "done" && state.phase !== "error" && (
                <motion.p
                  key={state.statusMessage}
                  initial={{ opacity: 0, y: 4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  transition={spring}
                  className="text-sm text-stone-400"
                >
                  {state.statusMessage}
                </motion.p>
              )}
            </AnimatePresence>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Live signal cards during streaming */}
      <AnimatePresence>
        {state.signals.length > 0 && state.phase !== "done" && (
          <motion.div
            key="live-signals"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          >
            <p className="mb-2 text-xs font-medium uppercase tracking-widest text-stone-500">
              Infrastructure Signals
            </p>
            <motion.div
              variants={staggerContainer}
              initial="hidden"
              animate="visible"
              className="grid grid-cols-1 gap-2 sm:grid-cols-2"
            >
              {state.signals.map((signal, i) => (
                <LiveSignalCard key={signal.signal} signal={signal} index={i} />
              ))}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Error state */}
      <AnimatePresence>
        {state.phase === "error" && state.error && (
          <motion.div
            key="error"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={spring}
            className="rounded-xl border border-red-900/60 bg-red-950/30 p-4"
          >
            <p className="text-sm font-medium text-red-400 mb-1">Analysis failed</p>
            <p className="text-sm text-red-300/80">{state.error.detail}</p>
            <button
              onClick={() => dispatch({ type: "RESET" })}
              className="mt-3 text-xs text-red-400 underline underline-offset-2 hover:text-red-300"
            >
              Try again
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Final scorecard */}
      <AnimatePresence>
        {state.phase === "done" && state.scorecard && (
          <motion.div
            key="scorecard"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={springGentle}
          >
            <SiteScorecard scorecard={state.scorecard} />

            <motion.button
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              transition={{ delay: 0.8 }}
              onClick={() => dispatch({ type: "RESET" })}
              className="mt-6 text-sm text-stone-500 underline underline-offset-2 hover:text-stone-400"
            >
              Analyze another site
            </motion.button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
