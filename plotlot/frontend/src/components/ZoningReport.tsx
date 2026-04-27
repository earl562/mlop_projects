"use client";

import { useState, useCallback } from "react";
import { ZoningReportData } from "@/lib/api";
import DensityBreakdown from "./DensityBreakdown";
import DocumentGenerator from "./DocumentGenerator";
import ParcelViewer from "./ParcelViewer";
import SetbackDiagram from "./SetbackDiagram";
import { useToast } from "./Toast";

interface ZoningReportProps {
  report: ZoningReportData;
}

const WELL_INDEXED = new Set([
  "miami gardens", "miami-dade county", "miami dade county",
  "boca raton", "miramar", "fort lauderdale",
]);

function getCoverageLevel(report: ZoningReportData): "full" | "partial" | "unknown" {
  const municipality = report.municipality;
  if (!municipality) return "unknown";
  if (report.confidence === "low" && !report.zoning_district && !report.numeric_params) {
    return "partial";
  }
  return WELL_INDEXED.has(municipality.toLowerCase()) ? "full" : "partial";
}

function CoverageBadge({ report }: { report: ZoningReportData }) {
  const level = getCoverageLevel(report);
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

function ConfidenceBadge({ level }: { level: string }) {
  const colors: Record<string, string> = {
    high: "bg-emerald-100 text-emerald-700 border-emerald-200",
    medium: "bg-amber-100 text-amber-700 border-amber-200",
    low: "bg-red-100 text-red-700 border-red-200",
  };
  return (
    <span className={`inline-flex rounded-full border px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wider ${colors[level] || colors.low}`}>
      {level}
    </span>
  );
}

function CollapsibleSection({ title, defaultOpen = true, children }: { title: string; defaultOpen?: boolean; children: React.ReactNode }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="space-y-3">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 text-left active:scale-[0.98]"
      >
        <span className="section-pill">{title}</span>
        <svg
          className={`h-3 w-3 text-[var(--text-muted)] transition-transform duration-200 ${open ? "rotate-90" : ""}`}
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path fillRule="evenodd" d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z" clipRule="evenodd" />
        </svg>
      </button>
      {open && <div className="animate-fade-in">{children}</div>}
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const { toast } = useToast();
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      toast("Copied to clipboard");
    } catch { /* clipboard API may be blocked */ }
  };
  return (
    <button
      onClick={handleCopy}
      className="inline-flex h-5 w-5 items-center justify-center rounded text-stone-300 transition-colors hover:text-[var(--text-muted)] active:scale-[0.98]"
      title="Copy"
    >
      <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
      </svg>
    </button>
  );
}

function DataRow({ label, value }: { label: string; value: string }) {
  if (!value || value === "null" || value === "undefined" || value === "Not specified") return null;
  return (
    <div className="flex justify-between gap-2 border-b border-[var(--border)] py-1.5">
      <span className="shrink-0 text-xs text-[var(--text-muted)] sm:text-sm">{label}</span>
      <span className="text-right text-xs font-medium text-[var(--text-primary)] sm:text-sm">{value}</span>
    </div>
  );
}

function UsesList({ title, uses, color }: { title: string; uses: string[] | string | null | undefined; color: string }) {
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
        {list.map((use, i) => (
          <span key={i} className={`rounded-md px-2 py-0.5 text-xs ${colors[color]}`}>
            {use}
          </span>
        ))}
      </div>
    </div>
  );
}

function parseNumericFt(value: string | undefined | null): number {
  if (!value) return 0;
  const match = value.match(/[\d.]+/);
  return match ? parseFloat(match[0]) : 0;
}


export default function ZoningReport({ report }: ZoningReportProps) {
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);

  const handleDownloadPDF = useCallback(async () => {
    if (pdfLoading) return;
    setPdfLoading(true);
    setPdfError(null);
    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const resp = await fetch(`${API_URL}/api/v1/geometry/report/pdf`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(report),
      });
      if (!resp.ok) throw new Error("PDF generation failed");
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `PlotLot_${(report.formatted_address || "report").replace(/[^a-zA-Z0-9]/g, "_").slice(0, 50)}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("PDF download failed:", err);
      setPdfError("PDF generation failed. Please try again.");
      setTimeout(() => setPdfError(null), 5000);
    } finally {
      setPdfLoading(false);
    }
  }, [report, pdfLoading]);

  // Setback values
  const setbackFront = report.numeric_params?.setback_front_ft || parseNumericFt(report.setbacks?.front);
  const setbackSide = report.numeric_params?.setback_side_ft || parseNumericFt(report.setbacks?.side);
  const setbackRear = report.numeric_params?.setback_rear_ft || parseNumericFt(report.setbacks?.rear);
  let lotWidth = report.density_analysis?.lot_width_ft || report.numeric_params?.min_lot_width_ft || 0;
  let lotDepth = report.density_analysis?.lot_depth_ft || 0;

  // Estimate lot dimensions from lot area when width/depth unavailable (typical 1:1.4 ratio)
  if (lotWidth <= 0 || lotDepth <= 0) {
    const lotArea = report.density_analysis?.lot_size_sqft || report.property_record?.lot_size_sqft || 0;
    if (lotArea > 0) {
      lotWidth = Math.round(Math.sqrt(lotArea / 1.4));
      lotDepth = Math.round(lotWidth * 1.4);
    }
  }

  const confidenceBorder = report.confidence === "low"
    ? "border-l-4 border-l-red-400"
    : report.confidence === "medium"
      ? "border-l-4 border-l-amber-400"
      : "";

  return (
    <div className="w-full space-y-6 rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)] p-5 sm:space-y-8 sm:rounded-3xl sm:p-8" style={{ boxShadow: "var(--shadow-card)" }}>
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="truncate font-display text-xl text-[var(--text-primary)] sm:text-2xl">{report.formatted_address}</h2>
            <CopyButton text={report.formatted_address} />
          </div>
          <p className="mt-1 text-xs text-[var(--text-muted)] sm:text-sm">
            {report.municipality}, {report.county} County
          </p>
          <div className="mt-2">
          <CoverageBadge report={report} />
          </div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-2">
          <ConfidenceBadge level={report.confidence} />
          {pdfError && (
            <p className="text-right text-[10px] text-red-500">{pdfError}</p>
          )}
          <button
            onClick={handleDownloadPDF}
            disabled={pdfLoading}
            className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center gap-2 rounded-full border border-[var(--border)] bg-[var(--bg-surface)] px-3 py-1.5 text-xs font-medium text-[var(--text-muted)] transition-colors hover:border-[var(--border-hover)] hover:text-[var(--text-secondary)] active:scale-[0.98] disabled:opacity-50 sm:min-h-0 sm:min-w-0"
            title="Download PDF report"
          >
            {pdfLoading ? (
              <svg className="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            ) : (
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
              </svg>
            )}
            PDF
          </button>
        </div>
      </div>

      {/* Parcel Viewer — unified split-panel with property details + interactive map */}
      {report.property_record && (
        <ParcelViewer report={report} />
      )}

      {/* Zoning district — with copy */}
      <div className="flex flex-wrap items-center gap-3 sm:gap-4">
        <span className="font-display text-3xl text-[var(--text-primary)] sm:text-4xl">{report.zoning_district}</span>
        <CopyButton text={report.zoning_district} />
        <span className="text-sm text-[var(--text-muted)]">{report.zoning_description}</span>
      </div>

      {/* Partial coverage callout */}
          {getCoverageLevel(report) === "partial" && !report.zoning_district && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/20 dark:text-amber-300">
          Zoning ordinance data isn&apos;t indexed for {report.municipality} yet.
          Property record and comparable sales data are still available.
        </div>
      )}

      {/* Confidence warning — inline next to header when not high */}
      {report.confidence !== "high" && (
        <div className={`flex items-center gap-2 rounded-lg ${confidenceBorder} bg-[var(--bg-surface-raised)] px-3 py-2`}>
          <svg className={`h-4 w-4 shrink-0 ${report.confidence === "low" ? "text-red-500" : "text-amber-500"}`} viewBox="0 0 20 20" fill="currentColor">
            <path fillRule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.168 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 9a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
          </svg>
          <span className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
            {report.confidence} confidence — verify with local zoning office
          </span>
        </div>
      )}

      {/* Max Allowable Units — hero, always visible */}
      {report.density_analysis && (() => {
        const buildW = lotWidth > 0 ? Math.max(0, lotWidth - 2 * setbackSide) : 0;
        const buildD = lotDepth > 0 ? Math.max(0, lotDepth - setbackFront - setbackRear) : 0;
        const footprint = buildW > 0 && buildD > 0 ? buildW * buildD : 0;
        const lotSize = report.density_analysis.lot_size_sqft || report.property_record?.lot_size_sqft || 0;
        const buildingArea = report.property_record?.building_area_sqft || 0;
        const coverageUsed = lotSize > 0 && buildingArea > 0 ? ((buildingArea / lotSize) * 100).toFixed(1) : null;
        return (
          <DensityBreakdown
            analysis={report.density_analysis}
            buildableFootprintSqft={footprint > 0 ? footprint : undefined}
            currentCoveragePct={coverageUsed}
          />
        );
      })()}

      {/* Property Type */}
      {report.numeric_params?.property_type && report.density_analysis && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="section-pill">Property Type</span>
          <span className="rounded-md bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-950/50 dark:text-amber-400">
            {report.numeric_params.property_type === "land" && "Land / Development"}
            {report.numeric_params.property_type === "single_family" && "Single-Family"}
            {report.numeric_params.property_type === "multifamily" && "Multifamily (2-4)"}
            {report.numeric_params.property_type === "commercial_mf" && "Commercial MF (5+)"}
            {report.numeric_params.property_type === "commercial" && "Commercial"}
          </span>
          <span className="text-xs text-[var(--text-muted)]">
            {report.density_analysis.max_units} unit{report.density_analysis.max_units !== 1 ? "s" : ""} on {(report.density_analysis.lot_size_sqft || report.property_record?.lot_size_sqft || 0).toLocaleString()} sqft
          </span>
        </div>
      )}

      {/* Dimensional Standards — collapsible, default open */}
      <CollapsibleSection title="Dimensional Standards" defaultOpen={true}>
        <div className="space-y-1">
          <DataRow label="Max Height" value={report.max_height} />
          <DataRow label="Max Density" value={report.max_density} />
          <DataRow label="Floor Area Ratio" value={report.floor_area_ratio} />
          <DataRow label="Lot Coverage" value={report.lot_coverage} />
          <DataRow label="Min Lot Size" value={report.min_lot_size} />
          <DataRow label="Parking" value={report.parking_requirements} />
        </div>
      </CollapsibleSection>

      {/* Setbacks — collapsible, default open, with 2D diagram */}
      {report.setbacks && [report.setbacks.front, report.setbacks.side, report.setbacks.rear].some((v) => v && v !== "null") && (
        <CollapsibleSection title="Setbacks" defaultOpen={true}>
          {lotWidth > 0 && lotDepth > 0 && (setbackFront > 0 || setbackSide > 0 || setbackRear > 0) && (
            <SetbackDiagram
              lotWidth={lotWidth}
              lotDepth={lotDepth}
              setbackFront={setbackFront}
              setbackSide={setbackSide}
              setbackRear={setbackRear}
            />
          )}
          <div className="grid grid-cols-3 gap-3">
            {[
              { label: "Front", value: report.setbacks.front },
              { label: "Side", value: report.setbacks.side },
              { label: "Rear", value: report.setbacks.rear },
            ].map((s) => {
              const display = s.value && s.value !== "null" ? s.value : "N/A";
              return (
                <div key={s.label} className="rounded-lg bg-[var(--bg-surface-raised)] p-2 text-center shadow-[inset_0_1px_3px_rgba(0,0,0,0.06)] sm:p-3">
                  <div className="text-xs text-[var(--text-muted)]">{s.label}</div>
                  <div className="mt-1 text-base font-semibold text-[var(--text-primary)] sm:text-lg">{display}</div>
                </div>
              );
            })}
          </div>
        </CollapsibleSection>
      )}

      {/* Permitted Uses — collapsible, default collapsed */}
      <CollapsibleSection title="Permitted Uses" defaultOpen={false}>
        <div className="space-y-3">
          <UsesList title="Allowed" uses={report.allowed_uses} color="green" />
          <UsesList title="Conditional" uses={report.conditional_uses} color="yellow" />
          <UsesList title="Prohibited" uses={report.prohibited_uses} color="red" />
        </div>
      </CollapsibleSection>

      {/* Comparable Sales */}
      {report.comp_analysis && report.comp_analysis.comparables && report.comp_analysis.comparables.length > 0 && (
        <CollapsibleSection title="Comparable Sales" defaultOpen={true}>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <div className="rounded-lg bg-[var(--bg-surface-raised)] p-3">
                <div className="text-xs text-[var(--text-muted)]">Median $/Acre</div>
                <div className="text-lg font-bold text-[var(--text-primary)]">
                  ${report.comp_analysis.median_price_per_acre.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </div>
              </div>
              <div className="rounded-lg bg-[var(--bg-surface-raised)] p-3">
                <div className="text-xs text-[var(--text-muted)]">Est. Land Value</div>
                <div className="text-lg font-bold text-[var(--text-primary)]">
                  ${report.comp_analysis.estimated_land_value.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </div>
              </div>
              <div className="rounded-lg bg-[var(--bg-surface-raised)] p-3">
                <div className="text-xs text-[var(--text-muted)]">Confidence</div>
                <div className="text-lg font-bold text-[var(--text-primary)]">
                  {(report.comp_analysis.confidence * 100).toFixed(0)}%
                </div>
              </div>
            </div>
            <div className="overflow-x-auto rounded-lg border border-[var(--border)]">
              <table className="min-w-full text-xs">
                <thead className="bg-[var(--bg-surface-raised)]">
                  <tr>
                    <th className="px-3 py-2 text-left font-semibold text-[var(--text-secondary)]">Address</th>
                    <th className="px-3 py-2 text-right font-semibold text-[var(--text-secondary)]">Price</th>
                    <th className="px-3 py-2 text-right font-semibold text-[var(--text-secondary)]">$/Acre</th>
                    <th className="px-3 py-2 text-right font-semibold text-[var(--text-secondary)]">Dist.</th>
                    <th className="px-3 py-2 text-left font-semibold text-[var(--text-secondary)]">Date</th>
                  </tr>
                </thead>
                <tbody>
                  {report.comp_analysis.comparables.map((comp, i) => (
                    <tr key={i} className="border-t border-[var(--border)]">
                      <td className="px-3 py-2 text-[var(--text-secondary)]">{comp.address || "N/A"}</td>
                      <td className="px-3 py-2 text-right font-medium text-[var(--text-primary)]">
                        ${comp.sale_price.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </td>
                      <td className="px-3 py-2 text-right text-[var(--text-secondary)]">
                        ${comp.price_per_acre.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </td>
                      <td className="px-3 py-2 text-right text-[var(--text-muted)]">
                        {comp.distance_miles.toFixed(1)} mi
                      </td>
                      <td className="px-3 py-2 text-[var(--text-muted)]">{comp.sale_date || "N/A"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </CollapsibleSection>
      )}

      {/* Land Pro Forma */}
      {report.pro_forma && report.pro_forma.max_land_price > 0 && (
        <CollapsibleSection title="Land Pro Forma" defaultOpen={true}>
          <div className="space-y-3">
            {/* Waterfall visualization */}
            <div className="space-y-2">
              {[
                { label: "Gross Dev. Value", value: report.pro_forma.gross_development_value, color: "bg-emerald-500" },
                { label: "Hard Costs", value: -report.pro_forma.hard_costs, color: "bg-red-400" },
                { label: "Soft Costs", value: -report.pro_forma.soft_costs, color: "bg-orange-400" },
                { label: "Builder Margin", value: -report.pro_forma.builder_margin, color: "bg-amber-400" },
              ].map((item) => {
                const maxVal = report.pro_forma!.gross_development_value;
                const width = Math.abs(item.value) / maxVal * 100;
                return (
                  <div key={item.label} className="flex items-center gap-3">
                    <div className="w-28 text-xs text-[var(--text-muted)] text-right shrink-0">{item.label}</div>
                    <div className="flex-1">
                      <div className={`h-6 rounded ${item.color}`} style={{ width: `${Math.max(width, 2)}%` }} />
                    </div>
                    <div className="w-24 text-xs font-medium text-[var(--text-secondary)] text-right shrink-0">
                      {item.value < 0 ? "-" : ""}${Math.abs(item.value).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                    </div>
                  </div>
                );
              })}
              <div className="flex items-center gap-3 border-t border-[var(--border)] pt-2">
                <div className="w-28 text-xs font-bold text-[var(--text-primary)] text-right shrink-0">Max Offer</div>
                <div className="flex-1">
                  <div
                    className="h-6 rounded bg-[var(--text-primary)]"
                    style={{ width: `${(report.pro_forma.max_land_price / report.pro_forma.gross_development_value) * 100}%` }}
                  />
                </div>
                <div className="w-24 text-sm font-bold text-[var(--text-primary)] text-right shrink-0">
                  ${report.pro_forma.max_land_price.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </div>
              </div>
            </div>

            {/* Key metrics */}
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <div className="rounded-lg bg-[var(--bg-surface-raised)] p-3">
                <div className="text-xs text-[var(--text-muted)]">Cost/Door</div>
                <div className="text-sm font-bold text-[var(--text-primary)]">
                  ${report.pro_forma.cost_per_door.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </div>
              </div>
              <div className="rounded-lg bg-[var(--bg-surface-raised)] p-3">
                <div className="text-xs text-[var(--text-muted)]">Construction $/SF</div>
                <div className="text-sm font-bold text-[var(--text-primary)]">
                  ${report.pro_forma.construction_cost_psf}
                </div>
              </div>
              <div className="rounded-lg bg-[var(--bg-surface-raised)] p-3">
                <div className="text-xs text-[var(--text-muted)]">Units</div>
                <div className="text-sm font-bold text-[var(--text-primary)]">
                  {report.pro_forma.max_units}
                </div>
              </div>
              <div className="rounded-lg bg-[var(--bg-surface-raised)] p-3">
                <div className="text-xs text-[var(--text-muted)]">$/Door (Offer)</div>
                <div className="text-sm font-bold text-[var(--text-primary)]">
                  ${report.pro_forma.max_units > 0
                    ? (report.pro_forma.max_land_price / report.pro_forma.max_units).toLocaleString(undefined, { maximumFractionDigits: 0 })
                    : "N/A"}
                </div>
              </div>
            </div>

            {/* Notes */}
            {report.pro_forma.notes && report.pro_forma.notes.length > 0 && (
              <div className="text-xs text-[var(--text-muted)] space-y-1">
                {report.pro_forma.notes.map((note, i) => (
                  <p key={i}>{note}</p>
                ))}
              </div>
            )}
          </div>
        </CollapsibleSection>
      )}

      {/* Document Generation */}
      <CollapsibleSection title="Generate Documents" defaultOpen={!!report.pro_forma}>
        <DocumentGenerator report={report} />
      </CollapsibleSection>

      {/* Sources — collapsible */}
      {report.sources.length > 0 && (
        <div className="space-y-2">
          <button
            onClick={() => setSourcesOpen(!sourcesOpen)}
            className="flex min-h-[44px] items-center gap-2 active:scale-[0.98]"
          >
            <span className="section-pill">
              View {report.sources.length} source{report.sources.length !== 1 ? "s" : ""}
            </span>
            <svg
              className={`h-3 w-3 text-[var(--text-muted)] transition-transform ${sourcesOpen ? "rotate-90" : ""}`}
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path fillRule="evenodd" d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z" clipRule="evenodd" />
            </svg>
          </button>
          {sourcesOpen && (
            <div className="space-y-1 animate-fade-in">
              {report.sources.map((source, i) => (
                <div key={i} className="text-xs text-[var(--text-muted)]">
                  {source}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Action bar */}
      <div className="border-t border-[var(--border)] pt-6 flex items-center justify-end gap-3">
        <button
          onClick={handleDownloadPDF}
          disabled={pdfLoading}
          className="inline-flex items-center gap-2 rounded-full bg-[var(--text-primary)] px-5 py-2.5 text-sm font-medium text-[var(--bg-primary)] transition-all hover:opacity-80 active:scale-[0.98] disabled:opacity-50"
        >
          {pdfLoading ? (
            <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          ) : (
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3" />
            </svg>
          )}
          Download PDF
        </button>
      </div>
    </div>
  );
}
