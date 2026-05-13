"use client";

import { motion } from "framer-motion";
import { DensityAnalysisData } from "@/lib/api";
import { springBar, springGentle, staggerContainer, staggerItem } from "@/lib/motion";

interface DensityBreakdownProps {
  analysis: DensityAnalysisData;
  buildableFootprintSqft?: number;
  currentCoveragePct?: string | null;
}

export default function DensityBreakdown({ analysis, buildableFootprintSqft, currentCoveragePct }: DensityBreakdownProps) {
  const isCommercial = analysis.max_gla_sqft != null;
  const maxRaw = Math.max(...analysis.constraints.map((c) => c.raw_value), 1);

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)] p-4 sm:p-6" style={{ boxShadow: "var(--shadow-card)" }}>
      <div className="mb-4 flex items-center justify-between gap-4 sm:mb-6">
        <div className="min-w-0">
          <span className="section-pill">
            {isCommercial ? "Max Gross Leasable Area" : "Max Allowable Units"}
          </span>
          <p className="mt-2 truncate text-xs text-[var(--text-muted)]">
            Governing: {analysis.governing_constraint}
          </p>
        </div>
        <motion.div
          initial={{ opacity: 0, scale: 0.85 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={springGentle}
          className="shrink-0 text-right"
        >
          <div className="font-display text-4xl text-[var(--text-primary)] sm:text-5xl">
            {isCommercial
              ? `${analysis.max_gla_sqft!.toLocaleString()}`
              : analysis.max_units}
          </div>
          <div className="mt-1 text-xs text-[var(--text-muted)]">
            {isCommercial ? "sqft GLA" : `${analysis.lot_size_sqft.toLocaleString()} sqft lot`}
          </div>
        </motion.div>
      </div>

      {/* Constraint bars — spring animated, governing bar first then stagger */}
      <motion.div
        className="space-y-3"
        variants={staggerContainer}
        initial="hidden"
        animate="visible"
      >
        {analysis.constraints.map((c, idx) => {
          const pct = Math.min((c.raw_value / maxRaw) * 100, 100);
          const delay = c.is_governing ? 0 : 0.15 + idx * 0.08;
          return (
            <motion.div key={c.name} variants={staggerItem}>
              <div className="mb-1 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-[var(--text-secondary)]">{c.name}</span>
                  {c.is_governing && (
                    <motion.span
                      initial={{ opacity: 0, scale: 0.8 }}
                      animate={{ opacity: 1, scale: 1 }}
                      transition={{ ...springGentle, delay: 0.3 }}
                      className="rounded-full bg-amber-200 px-2 py-0.5 text-xs font-bold uppercase tracking-wide text-amber-800"
                    >
                      GOVERNING
                    </motion.span>
                  )}
                </div>
                <span className="text-xs font-mono text-stone-500">
                  {isCommercial
                    ? `${c.max_units.toLocaleString()} sqft`
                    : `${c.max_units} unit${c.max_units !== 1 ? "s" : ""}`}
                </span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-[var(--bg-surface-raised)]">
                <motion.div
                  className={`h-full rounded-full ${
                    c.is_governing
                      ? "bg-gradient-to-r from-amber-400 to-amber-600"
                      : "bg-stone-400"
                  }`}
                  initial={{ width: 0 }}
                  animate={{ width: `${pct}%` }}
                  transition={{ ...springBar, delay }}
                />
              </div>
              <p className="mt-0.5 truncate text-xs text-stone-500 font-mono">{c.formula}</p>
            </motion.div>
          );
        })}
      </motion.div>

      {/* Compact stats from development summary */}
      {(buildableFootprintSqft || currentCoveragePct) && (
        <div className="mt-4 flex flex-wrap gap-3 border-t border-[var(--border)] pt-3">
          {buildableFootprintSqft != null && buildableFootprintSqft > 0 && (
            <div className="text-xs text-[var(--text-muted)]">
              <span className="font-medium text-[var(--text-secondary)]">{Math.round(buildableFootprintSqft).toLocaleString()} sqft</span> buildable footprint
            </div>
          )}
          {currentCoveragePct && (
            <div className="text-xs text-[var(--text-muted)]">
              <span className="font-medium text-[var(--text-secondary)]">{currentCoveragePct}%</span> current coverage
            </div>
          )}
        </div>
      )}

      {analysis.notes.length > 0 && (
        <div className="mt-3 space-y-1">
          {analysis.notes.map((note, i) => (
            <p key={i} className="text-xs text-stone-500">
              {note}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
