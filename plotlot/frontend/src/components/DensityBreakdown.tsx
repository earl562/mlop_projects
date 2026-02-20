"use client";

import { DensityAnalysisData } from "@/lib/api";

interface DensityBreakdownProps {
  analysis: DensityAnalysisData;
}

export default function DensityBreakdown({ analysis }: DensityBreakdownProps) {
  const maxRaw = Math.max(...analysis.constraints.map((c) => c.raw_value), 1);

  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50/50 p-5">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-wider text-amber-700">
            Max Allowable Units
          </h3>
          <p className="mt-0.5 text-xs text-stone-500">
            Governing constraint: {analysis.governing_constraint}
          </p>
        </div>
        <div className="text-right">
          <div
            className="text-4xl font-black text-amber-700"
            style={{ textShadow: "0 1px 2px rgba(180, 83, 9, 0.15)" }}
          >
            {analysis.max_units}
          </div>
          <div className="text-xs text-stone-500">
            {analysis.lot_size_sqft.toLocaleString()} sqft lot
          </div>
        </div>
      </div>

      {/* Constraint bars */}
      <div className="space-y-2.5">
        {analysis.constraints.map((c) => {
          const pct = Math.min((c.raw_value / maxRaw) * 100, 100);
          return (
            <div key={c.name}>
              <div className="mb-1 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium text-stone-700">{c.name}</span>
                  {c.is_governing && (
                    <span className="rounded-full bg-amber-200 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-amber-800">
                      GOVERNING
                    </span>
                  )}
                </div>
                <span className="text-xs font-mono text-stone-500">
                  {c.max_units} unit{c.max_units !== 1 ? "s" : ""}
                </span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-stone-200">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${
                    c.is_governing
                      ? "bg-gradient-to-r from-amber-400 to-amber-600"
                      : "bg-stone-400"
                  }`}
                  style={{ width: `${pct}%` }}
                />
              </div>
              <p className="mt-0.5 text-[10px] text-stone-500 font-mono">{c.formula}</p>
            </div>
          );
        })}
      </div>

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
