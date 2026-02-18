"use client";

import { DensityAnalysisData } from "@/lib/api";

interface DensityBreakdownProps {
  analysis: DensityAnalysisData;
}

export default function DensityBreakdown({ analysis }: DensityBreakdownProps) {
  const maxRaw = Math.max(...analysis.constraints.map((c) => c.raw_value), 1);

  return (
    <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-5">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-sm font-semibold uppercase tracking-wider text-emerald-400">
            Max Allowable Units
          </h3>
          <p className="mt-0.5 text-xs text-zinc-500">
            Governing constraint: {analysis.governing_constraint}
          </p>
        </div>
        <div className="text-right">
          <div className="text-4xl font-black text-emerald-400">{analysis.max_units}</div>
          <div className="text-xs text-zinc-500">
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
                  <span className="text-xs font-medium text-zinc-300">{c.name}</span>
                  {c.is_governing && (
                    <span className="rounded-full bg-emerald-500/20 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-400">
                      GOVERNING
                    </span>
                  )}
                </div>
                <span className="text-xs font-mono text-zinc-400">
                  {c.max_units} unit{c.max_units !== 1 ? "s" : ""}
                </span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-zinc-800">
                <div
                  className={`h-full rounded-full transition-all duration-500 ${
                    c.is_governing ? "bg-emerald-500" : "bg-zinc-600"
                  }`}
                  style={{ width: `${pct}%` }}
                />
              </div>
              <p className="mt-0.5 text-[10px] text-zinc-600 font-mono">{c.formula}</p>
            </div>
          );
        })}
      </div>

      {analysis.notes.length > 0 && (
        <div className="mt-3 space-y-1">
          {analysis.notes.map((note, i) => (
            <p key={i} className="text-xs text-zinc-500">
              {note}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
