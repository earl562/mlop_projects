"use client";

import type { ZoningReportData, SourceRefData } from "@/lib/api";
import { useState } from "react";
import { useToast } from "./Toast";

// ---------------------------------------------------------------------------
// Coverage
// ---------------------------------------------------------------------------

export const WELL_INDEXED = new Set([
  "miami gardens", "miami-dade county", "miami dade county",
  "boca raton", "miramar", "fort lauderdale",
]);

export function getCoverageLevel(municipality: string | undefined): "full" | "partial" | "unknown" {
  if (!municipality) return "unknown";
  return WELL_INDEXED.has(municipality.toLowerCase()) ? "full" : "partial";
}

export function CoverageBadge({ municipality }: { municipality: string | undefined }) {
  const level = getCoverageLevel(municipality);
  if (level === "unknown") return null;
  if (level === "full") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-400">
        <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
        Full zoning coverage
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2.5 py-0.5 text-xs font-medium text-amber-700 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-400">
      <span className="text-[10px] leading-none">◐</span>
      Partial coverage — zoning data may be limited
    </span>
  );
}

// ---------------------------------------------------------------------------
// Confidence
// ---------------------------------------------------------------------------

export function ConfidenceBadge({ level }: { level: string }) {
  const colors: Record<string, string> = {
    high: "bg-emerald-100 text-emerald-700 border-emerald-200 dark:bg-emerald-950/40 dark:text-emerald-400 dark:border-emerald-800",
    medium: "bg-amber-100 text-amber-700 border-amber-200 dark:bg-amber-950/40 dark:text-amber-400 dark:border-amber-800",
    low: "bg-red-100 text-red-700 border-red-200 dark:bg-red-950/40 dark:text-red-400 dark:border-red-800",
  };
  return (
    <span className={`inline-flex rounded-full border px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wider ${colors[level] || colors.low}`}>
      {level}
    </span>
  );
}

// ---------------------------------------------------------------------------
// CopyButton
// ---------------------------------------------------------------------------

export function CopyButton({ text }: { text: string }) {
  const { toast } = useToast();
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      toast("Copied to clipboard");
    } catch { /* clipboard API may be blocked */ }
  };
  return (
    <button
      type="button"
      onClick={handleCopy}
      className="inline-flex h-8 w-8 items-center justify-center rounded text-stone-300 transition-colors hover:text-[var(--text-muted)] active:scale-[0.98] sm:h-5 sm:w-5"
      title="Copy"
      aria-label="Copy to clipboard"
    >
      <svg aria-hidden="true" className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
      </svg>
    </button>
  );
}

// ---------------------------------------------------------------------------
// DataRow + CitationBadge
// ---------------------------------------------------------------------------

export function CitationBadge({ sourceRef, index }: { sourceRef: SourceRefData; index: number }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline-block">
      <button
        type="button"
        onClick={() => setOpen((p) => !p)}
        className="ml-1 inline-flex h-4 w-4 items-center justify-center rounded-full bg-blue-100 text-[9px] font-bold text-blue-700 transition-colors hover:bg-blue-200 dark:bg-blue-900/40 dark:text-blue-400 dark:hover:bg-blue-800/40"
        aria-label={`Source ${index + 1}: ${sourceRef.section_title}`}
      >
        {index + 1}
      </button>
      {open && (
        <div className="absolute right-0 top-full z-50 mt-1 w-72 rounded-lg border border-[var(--border)] bg-[var(--bg-surface)] p-3 shadow-lg sm:w-80">
          <div className="mb-1 flex items-center justify-between">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-blue-600 dark:text-blue-400">
              Source {index + 1}
            </span>
            <button type="button" onClick={() => setOpen(false)} className="text-[var(--text-muted)] hover:text-[var(--text-secondary)]">
              <svg aria-hidden="true" className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          {sourceRef.section_title && <p className="mb-1 text-xs font-medium text-[var(--text-primary)]">{sourceRef.section_title}</p>}
          {sourceRef.section && <p className="mb-1 text-[10px] text-[var(--text-muted)]">{sourceRef.section}</p>}
          {sourceRef.chunk_text_preview && (
            <p className="text-xs leading-relaxed text-[var(--text-secondary)]">&ldquo;{sourceRef.chunk_text_preview}&rdquo;</p>
          )}
        </div>
      )}
    </span>
  );
}

export function DataRow({ label, value, citation }: {
  label: string;
  value: string;
  citation?: SourceRefData & { index: number };
}) {
  if (!value || value === "null" || value === "undefined" || value === "Not specified") return null;
  return (
    <div className="flex justify-between gap-2 border-b border-[var(--border)] py-1.5">
      <span className="shrink-0 text-xs text-[var(--text-muted)] sm:text-sm">{label}</span>
      <span className="flex items-center gap-0.5 text-right text-xs font-medium text-[var(--text-primary)] sm:text-sm">
        {value}
        {citation && <CitationBadge sourceRef={citation} index={citation.index} />}
      </span>
    </div>
  );
}

// ---------------------------------------------------------------------------
// UsesList
// ---------------------------------------------------------------------------

export function UsesList({ title, uses, color }: {
  title: string;
  uses: string[] | string | null | undefined;
  color: string;
}) {
  let list: string[];
  if (Array.isArray(uses)) {
    list = uses;
  } else if (typeof uses === "string") {
    try {
      const parsed = JSON.parse(uses);
      list = Array.isArray(parsed) ? parsed : [uses];
    } catch {
      list = uses ? [uses] : [];
    }
  } else {
    list = [];
  }
  if (!list.length) return null;
  const colors: Record<string, string> = {
    green: "bg-emerald-50 text-emerald-700",
    yellow: "bg-amber-50 text-amber-700",
    red: "bg-red-50 text-red-700",
  };
  return (
    <div>
      <h4 className="mb-1.5 text-xs font-medium text-[var(--text-muted)]">{title}</h4>
      <div className="flex flex-wrap gap-2">
        {list.map((use) => (
          <span key={use} className={`rounded-md px-2 py-0.5 text-xs ${colors[color]}`}>{use}</span>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Utilities
// ---------------------------------------------------------------------------

export function parseNumericFt(value: string | undefined | null): number {
  if (!value) return 0;
  const match = value.match(/[\d.]+/);
  return match ? parseFloat(match[0]) : 0;
}

export function estimateLotDimensions(report: ZoningReportData): { lotWidth: number; lotDepth: number } {
  let lotWidth = report.density_analysis?.lot_width_ft || report.numeric_params?.min_lot_width_ft || 0;
  let lotDepth = report.density_analysis?.lot_depth_ft || 0;
  if (lotWidth <= 0 || lotDepth <= 0) {
    const lotArea = report.density_analysis?.lot_size_sqft || report.property_record?.lot_size_sqft || 0;
    if (lotArea > 0) {
      lotWidth = Math.round(Math.sqrt(lotArea / 1.4));
      lotDepth = Math.round(lotWidth * 1.4);
    }
  }
  return { lotWidth, lotDepth };
}

// ---------------------------------------------------------------------------
// Comparable Sales section
// ---------------------------------------------------------------------------

export function ComparableSalesSection({ report }: { report: ZoningReportData }) {
  const comp = report.comp_analysis;
  if (!comp?.comparables?.length) return null;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {[
          { label: "Median $/Acre", value: `$${comp.median_price_per_acre.toLocaleString(undefined, { maximumFractionDigits: 0 })}` },
          { label: "Est. Land Value", value: `$${comp.estimated_land_value.toLocaleString(undefined, { maximumFractionDigits: 0 })}` },
          { label: "Confidence", value: `${(comp.confidence * 100).toFixed(0)}%` },
        ].map(({ label, value }) => (
          <div key={label} className="rounded-lg bg-[var(--bg-surface-raised)] p-3">
            <div className="text-xs text-[var(--text-muted)]">{label}</div>
            <div className="text-lg font-bold text-[var(--text-primary)]">{value}</div>
          </div>
        ))}
      </div>
      <div className="overflow-x-auto rounded-lg border border-[var(--border)]">
        <table className="min-w-full text-xs">
          <thead className="bg-[var(--bg-surface-raised)]">
            <tr>
              {["Address", "Price", "$/Acre", "Dist.", "Date"].map((h, i) => (
                <th key={h} className={`px-3 py-2 font-semibold text-[var(--text-secondary)] ${i === 0 ? "text-left" : i === 4 ? "text-left" : "text-right"}`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {comp.comparables.map((c) => (
              <tr key={`${c.address}-${c.sale_date}-${c.sale_price}`} className="border-t border-[var(--border)]">
                <td className="px-3 py-2 text-[var(--text-secondary)]">{c.address || "N/A"}</td>
                <td className="px-3 py-2 text-right font-medium text-[var(--text-primary)]">${c.sale_price.toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                <td className="px-3 py-2 text-right text-[var(--text-secondary)]">${c.price_per_acre.toLocaleString(undefined, { maximumFractionDigits: 0 })}</td>
                <td className="px-3 py-2 text-right text-[var(--text-muted)]">{c.distance_miles.toFixed(1)} mi</td>
                <td className="px-3 py-2 text-[var(--text-muted)]">{c.sale_date || "N/A"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pro Forma waterfall section
// ---------------------------------------------------------------------------

export function ProFormaSection({ report }: { report: ZoningReportData }) {
  const pf = report.pro_forma;
  if (!pf || pf.max_land_price <= 0) return null;
  const rows = [
    { label: "Gross Dev. Value", value: pf.gross_development_value, color: "bg-emerald-500" },
    { label: "Hard Costs", value: -pf.hard_costs, color: "bg-red-400" },
    { label: "Soft Costs", value: -pf.soft_costs, color: "bg-orange-400" },
    { label: "Builder Margin", value: -pf.builder_margin, color: "bg-amber-400" },
  ];
  return (
    <div className="space-y-3">
      <div className="space-y-2">
        {rows.map((item) => {
          const width = (Math.abs(item.value) / pf.gross_development_value) * 100;
          return (
            <div key={item.label} className="flex items-center gap-3">
              <div className="w-28 shrink-0 text-right text-xs text-[var(--text-muted)]">{item.label}</div>
              <div className="flex-1"><div className={`h-6 rounded ${item.color}`} style={{ width: `${Math.max(width, 2)}%` }} /></div>
              <div className="w-24 shrink-0 text-right text-xs font-medium text-[var(--text-secondary)]">
                {item.value < 0 ? "-" : ""}${Math.abs(item.value).toLocaleString(undefined, { maximumFractionDigits: 0 })}
              </div>
            </div>
          );
        })}
        <div className="flex items-center gap-3 border-t border-[var(--border)] pt-2">
          <div className="w-28 shrink-0 text-right text-xs font-bold text-[var(--text-primary)]">Max Offer</div>
          <div className="flex-1">
            <div className="h-6 rounded bg-[var(--text-primary)]" style={{ width: `${(pf.max_land_price / pf.gross_development_value) * 100}%` }} />
          </div>
          <div className="w-24 shrink-0 text-right text-sm font-bold text-[var(--text-primary)]">
            ${pf.max_land_price.toLocaleString(undefined, { maximumFractionDigits: 0 })}
          </div>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {[
          { label: "Cost/Door", value: `$${pf.cost_per_door.toLocaleString(undefined, { maximumFractionDigits: 0 })}` },
          { label: "Construction $/SF", value: `$${pf.construction_cost_psf}` },
          { label: "Units", value: pf.max_units.toString() },
          { label: "$/Door (Offer)", value: pf.max_units > 0 ? `$${(pf.max_land_price / pf.max_units).toLocaleString(undefined, { maximumFractionDigits: 0 })}` : "N/A" },
        ].map(({ label, value }) => (
          <div key={label} className="rounded-lg bg-[var(--bg-surface-raised)] p-3">
            <div className="text-xs text-[var(--text-muted)]">{label}</div>
            <div className="text-sm font-bold text-[var(--text-primary)]">{value}</div>
          </div>
        ))}
      </div>
      {pf.notes && pf.notes.length > 0 && (
        <div className="space-y-1 text-xs text-[var(--text-muted)]">
          {pf.notes.map((note) => <p key={note}>{note}</p>)}
        </div>
      )}
    </div>
  );
}
