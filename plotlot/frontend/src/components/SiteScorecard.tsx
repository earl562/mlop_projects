"use client";

import { AnimatePresence, motion } from "framer-motion";
import { spring, springBar, springGentle, staggerContainer, staggerItem } from "@/lib/motion";
import type { InfraSignalData, SiteScorecardData } from "@/lib/api";

interface SiteScorecardProps {
  scorecard: SiteScorecardData;
}

// ---------------------------------------------------------------------------
// Rating badge
// ---------------------------------------------------------------------------

const RATING_STYLES: Record<string, string> = {
  Excellent: "bg-emerald-500/15 text-emerald-400 ring-1 ring-emerald-500/30",
  Good: "bg-amber-500/15 text-amber-400 ring-1 ring-amber-500/30",
  Fair: "bg-yellow-500/15 text-yellow-600 dark:text-yellow-400 ring-1 ring-yellow-500/30",
  Poor: "bg-red-500/15 text-red-400 ring-1 ring-red-500/30",
  Disqualified: "bg-red-600/20 text-red-400 ring-1 ring-red-600/40",
};

function RatingBadge({ rating }: { rating: string }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold tabular-nums ${RATING_STYLES[rating] ?? "bg-stone-500/15 text-stone-400"}`}
    >
      {rating}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Score bar — spring-animated, amber accent on governing bar
// ---------------------------------------------------------------------------

interface ScoreBarProps {
  score: number; // 0–1
  rating: string;
  delay?: number;
}

function ScoreBar({ score, rating, delay = 0 }: ScoreBarProps) {
  const isDisqualified = rating === "Disqualified" || score === 0;
  const barColor = isDisqualified
    ? "bg-red-500"
    : score >= 0.85
      ? "bg-emerald-500"
      : score >= 0.70
        ? "bg-amber-500"
        : score >= 0.50
          ? "bg-yellow-500"
          : "bg-red-500";

  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-stone-800">
      <motion.div
        className={`h-full rounded-full ${barColor}`}
        initial={{ width: 0 }}
        animate={{ width: isDisqualified ? "100%" : `${score * 100}%` }}
        transition={{ ...springBar, delay }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Signal card
// ---------------------------------------------------------------------------

interface SignalCardProps {
  signal: InfraSignalData;
  index: number;
}

const SIGNAL_ICONS: Record<string, string> = {
  power_grid: "⚡",
  fiber: "🌐",
  flood_zone: "🌊",
  seismic: "🏔",
  zoning: "📋",
};

function SignalCard({ signal, index }: SignalCardProps) {
  return (
    <motion.div
      variants={staggerItem}
      className="group rounded-xl border border-stone-800 bg-stone-900/60 p-4 hover:border-stone-700 transition-colors"
    >
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-base leading-none select-none shrink-0" aria-hidden>
            {SIGNAL_ICONS[signal.name] ?? "●"}
          </span>
          <span className="text-sm font-medium text-stone-200 truncate">{signal.label}</span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-sm font-semibold tabular-nums text-stone-300">
            {Math.round(signal.score * 100)}%
          </span>
          <RatingBadge rating={signal.rating} />
        </div>
      </div>

      <ScoreBar score={signal.score} rating={signal.rating} delay={index * 0.06} />

      <p className="mt-2.5 text-xs leading-relaxed text-stone-400">{signal.summary}</p>

      <p className="mt-1.5 text-[11px] text-stone-600">
        Source: {signal.source}
        {signal.confidence !== "high" && (
          <span className="ml-1.5 text-yellow-600/80">· {signal.confidence} confidence</span>
        )}
      </p>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Composite ring — large score display
// ---------------------------------------------------------------------------

interface CompositeRingProps {
  score: number;
  rating: string;
}

function CompositeRing({ score, rating }: CompositeRingProps) {
  const isDisqualified = rating === "Disqualified";
  const displayPct = isDisqualified ? 0 : Math.round(score * 100);

  const ratingColor = isDisqualified
    ? "text-red-400"
    : score >= 0.85
      ? "text-emerald-400"
      : score >= 0.70
        ? "text-amber-400"
        : score >= 0.50
          ? "text-yellow-400"
          : "text-red-400";

  return (
    <div className="flex flex-col items-center justify-center py-6">
      <motion.div
        initial={{ opacity: 0, scale: 0.8 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={springGentle}
        className="relative flex h-28 w-28 items-center justify-center"
      >
        {/* Background ring */}
        <svg className="absolute inset-0 -rotate-90" viewBox="0 0 80 80">
          <circle cx="40" cy="40" r="32" fill="none" stroke="currentColor" strokeWidth="6" className="text-stone-800" />
          <motion.circle
            cx="40" cy="40" r="32"
            fill="none"
            stroke="currentColor"
            strokeWidth="6"
            strokeLinecap="round"
            strokeDasharray={`${2 * Math.PI * 32}`}
            initial={{ strokeDashoffset: 2 * Math.PI * 32 }}
            animate={{ strokeDashoffset: isDisqualified ? 2 * Math.PI * 32 : (1 - score) * 2 * Math.PI * 32 }}
            transition={{ ...springBar, delay: 0.2 }}
            className={ratingColor}
          />
        </svg>
        <div className="relative flex flex-col items-center">
          <motion.span
            className={`text-3xl font-bold tabular-nums ${ratingColor}`}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.4 }}
          >
            {isDisqualified ? "—" : `${displayPct}`}
          </motion.span>
          {!isDisqualified && (
            <span className="text-xs text-stone-500 -mt-0.5">/ 100</span>
          )}
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ ...springGentle, delay: 0.5 }}
        className="mt-3 text-center"
      >
        <RatingBadge rating={rating} />
        <p className="mt-1 text-xs text-stone-500">Site Score</p>
      </motion.div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main SiteScorecard component
// ---------------------------------------------------------------------------

export function SiteScorecard({ scorecard }: SiteScorecardProps) {
  const signals = [
    scorecard.power_signal,
    scorecard.fiber_signal,
    scorecard.flood_signal,
    scorecard.seismic_signal,
    scorecard.zoning_signal,
  ].filter((s): s is InfraSignalData => s !== null);

  const hasDisqualifiers = scorecard.deal_breakers.length > 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={springGentle}
        className="rounded-2xl border border-stone-800 bg-stone-900/80 p-6"
      >
        <div className="flex flex-col sm:flex-row sm:items-start gap-6">
          {/* Composite score ring */}
          <div className="shrink-0">
            <CompositeRing score={scorecard.composite_score} rating={scorecard.composite_rating || "Fair"} />
          </div>

          {/* Summary */}
          <div className="flex-1 min-w-0 py-4">
            <div className="mb-1 flex items-center gap-2">
              <span className="text-xs font-medium uppercase tracking-widest text-stone-500">
                Data Center Site Analysis
              </span>
            </div>
            <h2 className="text-lg font-semibold text-stone-100 leading-snug mb-1 truncate">
              {scorecard.formatted_address || scorecard.address}
            </h2>
            <p className="text-sm text-stone-400 mb-3">
              {scorecard.municipality}, {scorecard.county} County
            </p>

            {scorecard.summary && (
              <p className="text-sm leading-relaxed text-stone-300">{scorecard.summary}</p>
            )}

            {/* Strengths */}
            <AnimatePresence>
              {scorecard.strengths.length > 0 && (
                <motion.div
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.3 }}
                  className="mt-3 flex flex-wrap gap-1.5"
                >
                  {scorecard.strengths.map((s, i) => (
                    <span
                      key={i}
                      className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2.5 py-0.5 text-xs text-emerald-400 ring-1 ring-emerald-500/20"
                    >
                      <span aria-hidden>✓</span> {s}
                    </span>
                  ))}
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        </div>

        {/* Deal breakers */}
        <AnimatePresence>
          {hasDisqualifiers && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              transition={spring}
              className="mt-4 rounded-xl border border-red-900/60 bg-red-950/30 p-4"
            >
              <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-red-400">
                Deal Breakers
              </p>
              <ul className="space-y-1">
                {scorecard.deal_breakers.map((d, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-red-300">
                    <span className="mt-0.5 shrink-0 text-red-500" aria-hidden>✗</span>
                    {d}
                  </li>
                ))}
              </ul>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>

      {/* Signal cards */}
      <div>
        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.2 }}
          className="mb-3 text-xs font-medium uppercase tracking-widest text-stone-500"
        >
          Infrastructure Signals
        </motion.p>

        <motion.div
          variants={staggerContainer}
          initial="hidden"
          animate="visible"
          className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3"
        >
          {signals.map((signal, i) => (
            <SignalCard key={signal.name} signal={signal} index={i} />
          ))}
        </motion.div>
      </div>

      {/* Zoning params detail */}
      <AnimatePresence>
        {scorecard.datacenter_params && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ ...springGentle, delay: 0.4 }}
            className="rounded-xl border border-stone-800 bg-stone-900/60 p-5"
          >
            <p className="mb-3 text-xs font-medium uppercase tracking-widest text-stone-500">
              Industrial Zoning Standards
            </p>
            <div className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-3 text-sm">
              {scorecard.datacenter_params.setback_front_ft !== null && (
                <div>
                  <span className="text-stone-500 text-xs">Front setback</span>
                  <p className="font-medium text-stone-200">{scorecard.datacenter_params.setback_front_ft} ft</p>
                </div>
              )}
              {scorecard.datacenter_params.setback_side_ft !== null && (
                <div>
                  <span className="text-stone-500 text-xs">Side setback</span>
                  <p className="font-medium text-stone-200">{scorecard.datacenter_params.setback_side_ft} ft</p>
                </div>
              )}
              {scorecard.datacenter_params.setback_rear_ft !== null && (
                <div>
                  <span className="text-stone-500 text-xs">Rear setback</span>
                  <p className="font-medium text-stone-200">{scorecard.datacenter_params.setback_rear_ft} ft</p>
                </div>
              )}
              {scorecard.datacenter_params.max_height_ft !== null && (
                <div>
                  <span className="text-stone-500 text-xs">Max height</span>
                  <p className="font-medium text-stone-200">{scorecard.datacenter_params.max_height_ft} ft</p>
                </div>
              )}
              {scorecard.datacenter_params.max_far !== null && (
                <div>
                  <span className="text-stone-500 text-xs">Max FAR</span>
                  <p className="font-medium text-stone-200">{scorecard.datacenter_params.max_far}</p>
                </div>
              )}
              {scorecard.datacenter_params.noise_limit_db !== null && (
                <div>
                  <span className="text-stone-500 text-xs">Noise limit</span>
                  <p className="font-medium text-stone-200">{scorecard.datacenter_params.noise_limit_db} dB(A)</p>
                </div>
              )}
              {scorecard.datacenter_params.outdoor_equipment_allowed !== null && (
                <div>
                  <span className="text-stone-500 text-xs">Outdoor equipment</span>
                  <p className="font-medium text-stone-200">
                    {scorecard.datacenter_params.outdoor_equipment_allowed ? "Permitted" : "Not permitted"}
                  </p>
                </div>
              )}
            </div>

            {scorecard.datacenter_params.utility_easement_notes && (
              <p className="mt-3 text-xs leading-relaxed text-stone-500">
                <span className="font-medium text-stone-400">Utility notes: </span>
                {scorecard.datacenter_params.utility_easement_notes}
              </p>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Sources */}
      {scorecard.sources.length > 0 && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.6 }}
          className="flex flex-wrap gap-1.5"
        >
          {scorecard.sources.map((src, i) => (
            <span
              key={i}
              className="rounded-md bg-stone-900 px-2 py-0.5 text-[11px] text-stone-500 ring-1 ring-stone-800"
            >
              {src}
            </span>
          ))}
        </motion.div>
      )}
    </div>
  );
}
