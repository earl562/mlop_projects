"use client";

import { useState, useCallback } from "react";
import { ZoningReportData } from "@/lib/api";
import DensityBreakdown from "./DensityBreakdown";
import EnvelopeViewerWrapper from "./EnvelopeViewerWrapper";
import FloorPlanViewer from "./FloorPlanViewer";
import PropertyCard from "./PropertyCard";
import SatelliteMap from "./SatelliteMap";

interface ZoningReportProps {
  report: ZoningReportData;
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

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <h3 className="text-sm font-semibold uppercase tracking-wider text-stone-500">{title}</h3>
      {children}
    </div>
  );
}

function DataRow({ label, value }: { label: string; value: string }) {
  if (!value || value === "null" || value === "undefined" || value === "Not specified") return null;
  return (
    <div className="flex justify-between gap-2 border-b border-stone-200 py-1.5">
      <span className="shrink-0 text-xs text-stone-500 sm:text-sm">{label}</span>
      <span className="text-right text-xs font-medium text-stone-800 sm:text-sm">{value}</span>
    </div>
  );
}

function UsesList({ title, uses, color }: { title: string; uses: string[] | string | null | undefined; color: string }) {
  let list: string[];
  if (Array.isArray(uses)) {
    list = uses;
  } else if (typeof uses === "string") {
    // Handle JSON-stringified arrays from backend (e.g. "[\"single-family\"]")
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
      <h4 className="mb-1.5 text-xs font-medium text-stone-500">{title}</h4>
      <div className="flex flex-wrap gap-1.5">
        {list.map((use, i) => (
          <span key={i} className={`rounded-md px-2 py-0.5 text-xs ${colors[color]}`}>
            {use}
          </span>
        ))}
      </div>
    </div>
  );
}

/** Parse a numeric feet value from a string like "25 ft" or "25" → 25 */
function parseNumericFt(value: string | undefined | null): number {
  if (!value) return 0;
  const match = value.match(/[\d.]+/);
  return match ? parseFloat(match[0]) : 0;
}

export default function ZoningReport({ report }: ZoningReportProps) {
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [pdfLoading, setPdfLoading] = useState(false);

  const handleDownloadPDF = useCallback(async () => {
    if (pdfLoading) return;
    setPdfLoading(true);
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
    } finally {
      setPdfLoading(false);
    }
  }, [report, pdfLoading]);

  return (
    <div className="w-full space-y-4 rounded-xl border-l-4 border-l-amber-400 border border-stone-200 bg-white p-4 shadow-sm sm:space-y-6 sm:p-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="truncate text-lg font-bold text-stone-800 sm:text-xl">{report.formatted_address}</h2>
          <p className="mt-1 text-xs text-stone-500 sm:text-sm">
            {report.municipality}, {report.county} County
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-2">
          <ConfidenceBadge level={report.confidence} />
          <button
            onClick={handleDownloadPDF}
            disabled={pdfLoading}
            className="inline-flex min-h-[44px] min-w-[44px] items-center justify-center gap-1.5 rounded-lg border border-stone-200 bg-white px-3 py-1.5 text-xs font-medium text-stone-600 shadow-sm transition-colors hover:bg-stone-50 hover:text-stone-800 disabled:opacity-50 sm:min-h-0 sm:min-w-0"
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

      {/* Satellite map */}
      {report.lat != null && report.lng != null && (
        <SatelliteMap lat={report.lat} lng={report.lng} address={report.formatted_address} />
      )}

      {/* Zoning district — prominent standalone line */}
      <div className="flex flex-wrap items-baseline gap-2 sm:gap-3">
        <span className="text-2xl font-black text-amber-700 sm:text-3xl">{report.zoning_district}</span>
        <span className="text-xs text-stone-500 sm:text-sm">{report.zoning_description}</span>
      </div>

      {/* Summary */}
      {report.summary && (
        <div className="rounded-lg bg-[#faf8f5] p-4 text-sm leading-relaxed text-stone-600">
          {report.summary}
        </div>
      )}

      {/* Density Analysis — hero section */}
      {report.density_analysis && (
        <DensityBreakdown analysis={report.density_analysis} />
      )}

      {/* Dimensional Standards */}
      <Section title="Dimensional Standards">
        <div className="space-y-0.5">
          <DataRow label="Max Height" value={report.max_height} />
          <DataRow label="Max Density" value={report.max_density} />
          <DataRow label="Floor Area Ratio" value={report.floor_area_ratio} />
          <DataRow label="Lot Coverage" value={report.lot_coverage} />
          <DataRow label="Min Lot Size" value={report.min_lot_size} />
          <DataRow label="Parking" value={report.parking_requirements} />
        </div>
      </Section>

      {/* Setbacks */}
      {report.setbacks && [report.setbacks.front, report.setbacks.side, report.setbacks.rear].some((v) => v && v !== "null") && (
        <Section title="Setbacks">
          <div className="grid grid-cols-3 gap-3">
            {[
              { label: "Front", value: report.setbacks.front },
              { label: "Side", value: report.setbacks.side },
              { label: "Rear", value: report.setbacks.rear },
            ].map((s) => {
              const display = s.value && s.value !== "null" ? s.value : "N/A";
              return (
              <div key={s.label} className="rounded-lg bg-stone-50 p-2 text-center shadow-[inset_0_1px_3px_rgba(0,0,0,0.06)] sm:p-3">
                <div className="text-[10px] text-stone-500 sm:text-xs">{s.label}</div>
                <div className="mt-0.5 text-base font-semibold text-stone-800 sm:mt-1 sm:text-lg">{display}</div>
              </div>
              );
            })}
          </div>
        </Section>
      )}

      {/* 3D Buildable Envelope Viewer */}
      {(() => {
        const lotWidth = report.density_analysis?.lot_width_ft
          || report.numeric_params?.min_lot_width_ft
          || 0;
        const lotDepth = report.density_analysis?.lot_depth_ft || 0;

        // Prefer numeric params, fall back to parsing string setbacks
        const setbackFront = report.numeric_params?.setback_front_ft
          || parseNumericFt(report.setbacks?.front);
        const setbackSide = report.numeric_params?.setback_side_ft
          || parseNumericFt(report.setbacks?.side);
        const setbackRear = report.numeric_params?.setback_rear_ft
          || parseNumericFt(report.setbacks?.rear);
        const maxHeight = report.numeric_params?.max_height_ft || 35;

        if (lotWidth > 0 && lotDepth > 0) {
          return (
            <Section title="3D Buildable Envelope">
              <EnvelopeViewerWrapper
                lotWidthFt={lotWidth}
                lotDepthFt={lotDepth}
                setbackFrontFt={setbackFront}
                setbackSideFt={setbackSide}
                setbackRearFt={setbackRear}
                maxHeightFt={maxHeight}
                buildableAreaSqft={report.density_analysis?.buildable_area_sqft ?? undefined}
              />
            </Section>
          );
        }
        return null;
      })()}

      {/* Floor Plan */}
      {(() => {
        const da = report.density_analysis;
        const np = report.numeric_params;
        if (!da?.buildable_area_sqft || !da?.lot_width_ft || !da?.lot_depth_ft) return null;

        const setbackFront = np?.setback_front_ft || parseNumericFt(report.setbacks?.front);
        const setbackSide = np?.setback_side_ft || parseNumericFt(report.setbacks?.side);
        const setbackRear = np?.setback_rear_ft || parseNumericFt(report.setbacks?.rear);
        const buildW = Math.max(0, (da.lot_width_ft || 0) - 2 * setbackSide);
        const buildD = Math.max(0, (da.lot_depth_ft || 0) - setbackFront - setbackRear);
        const maxHeight = np?.max_height_ft || 35;

        if (buildW <= 0 || buildD <= 0) return null;

        return (
          <Section title="Floor Plan">
            <FloorPlanViewer
              buildableWidthFt={buildW}
              buildableDepthFt={buildD}
              maxHeightFt={maxHeight}
              maxUnits={da.max_units || 1}
            />
          </Section>
        );
      })()}

      {/* Uses */}
      <Section title="Permitted Uses">
        <div className="space-y-3">
          <UsesList title="Allowed" uses={report.allowed_uses} color="green" />
          <UsesList title="Conditional" uses={report.conditional_uses} color="yellow" />
          <UsesList title="Prohibited" uses={report.prohibited_uses} color="red" />
        </div>
      </Section>

      {/* Property Record */}
      {report.property_record && (
        <PropertyCard record={report.property_record} />
      )}

      {/* Sources — collapsible */}
      {report.sources.length > 0 && (
        <div className="space-y-2">
          <button
            onClick={() => setSourcesOpen(!sourcesOpen)}
            className="flex min-h-[44px] items-center gap-1.5 text-sm font-semibold uppercase tracking-wider text-stone-500 transition-colors hover:text-stone-700"
          >
            <svg
              className={`h-3.5 w-3.5 transition-transform ${sourcesOpen ? "rotate-90" : ""}`}
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path fillRule="evenodd" d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z" clipRule="evenodd" />
            </svg>
            View {report.sources.length} source{report.sources.length !== 1 ? "s" : ""}
          </button>
          {sourcesOpen && (
            <div className="space-y-1 animate-fade-in">
              {report.sources.map((source, i) => (
                <div key={i} className="text-xs text-stone-500">
                  {source}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
