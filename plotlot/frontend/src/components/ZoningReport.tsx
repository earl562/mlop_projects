"use client";

import { useState, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ZoningReportData } from "@/lib/api";
import DensityBreakdown from "./DensityBreakdown";
import EnvelopeViewerWrapper from "./EnvelopeViewerWrapper";
import FloorPlanViewer from "./FloorPlanViewer";
import PropertyCard from "./PropertyCard";
import SatelliteMap from "./SatelliteMap";
import SetbackDiagram from "./SetbackDiagram";
import StreetView from "./StreetView";
import PropertyIntelligence from "./PropertyIntelligence";
import { useToast } from "./Toast";

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

const mdComponents = {
  p: ({ children }: { children?: React.ReactNode }) => <p className="mb-2 last:mb-0">{children}</p>,
  strong: ({ children }: { children?: React.ReactNode }) => <strong className="font-semibold text-[var(--text-primary)]">{children}</strong>,
  ul: ({ children }: { children?: React.ReactNode }) => <ul className="mb-2 ml-4 list-disc space-y-1">{children}</ul>,
  ol: ({ children }: { children?: React.ReactNode }) => <ol className="mb-2 ml-4 list-decimal space-y-1">{children}</ol>,
  li: ({ children }: { children?: React.ReactNode }) => <li>{children}</li>,
};

export default function ZoningReport({ report }: ZoningReportProps) {
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [summaryExpanded, setSummaryExpanded] = useState(false);

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

  const maxUnits = report.density_analysis?.max_units ?? 1;

  // Setback values
  const setbackFront = report.numeric_params?.setback_front_ft || parseNumericFt(report.setbacks?.front);
  const setbackSide = report.numeric_params?.setback_side_ft || parseNumericFt(report.setbacks?.side);
  const setbackRear = report.numeric_params?.setback_rear_ft || parseNumericFt(report.setbacks?.rear);
  const lotWidth = report.density_analysis?.lot_width_ft || report.numeric_params?.min_lot_width_ft || 0;
  const lotDepth = report.density_analysis?.lot_depth_ft || 0;

  // Summary collapsibility
  const summaryWords = report.summary ? report.summary.split(/\s+/).length : 0;
  const isLongSummary = summaryWords > 150;
  const displaySummary = isLongSummary && !summaryExpanded
    ? report.summary.split(/\s+/).slice(0, 150).join(" ") + "..."
    : report.summary;

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
        </div>
        <div className="flex shrink-0 flex-col items-end gap-2">
          <ConfidenceBadge level={report.confidence} />
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

      {/* Satellite map */}
      {report.lat != null && report.lng != null && (
        <SatelliteMap lat={report.lat} lng={report.lng} address={report.formatted_address} parcelGeometry={report.property_record?.parcel_geometry} />
      )}

      {/* Street View */}
      {report.lat != null && report.lng != null && (
        <StreetView lat={report.lat} lng={report.lng} address={report.formatted_address} />
      )}

      {/* Zoning district — with copy */}
      <div className="flex flex-wrap items-center gap-3 sm:gap-4">
        <span className="font-display text-3xl text-[var(--text-primary)] sm:text-4xl">{report.zoning_district}</span>
        <CopyButton text={report.zoning_district} />
        <span className="text-sm text-[var(--text-muted)]">{report.zoning_description}</span>
      </div>

      {/* Summary — markdown rendered, collapsible if long */}
      {report.summary && (
        <div className={`rounded-lg ${confidenceBorder} bg-[var(--bg-surface-raised)] p-4`}>
          {report.confidence !== "high" && (
            <div className="mb-2 flex items-center gap-2">
              <svg className={`h-4 w-4 ${report.confidence === "low" ? "text-red-500" : "text-amber-500"}`} viewBox="0 0 20 20" fill="currentColor">
                <path fillRule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.168 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 9a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
              </svg>
              <span className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                {report.confidence} confidence
              </span>
            </div>
          )}
          <div className="text-sm leading-relaxed text-[var(--text-secondary)]">
            <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>
              {displaySummary}
            </ReactMarkdown>
          </div>
          {isLongSummary && (
            <button
              onClick={() => setSummaryExpanded(!summaryExpanded)}
              className="mt-2 text-xs font-medium text-amber-700 transition-colors hover:text-amber-600 active:scale-[0.98]"
            >
              {summaryExpanded ? "Show less" : "Show full analysis"}
            </button>
          )}
        </div>
      )}

      {/* Max Allowable Units — hero, always visible */}
      {report.density_analysis && (
        <DensityBreakdown analysis={report.density_analysis} />
      )}

      {/* Financial Summary */}
      {report.numeric_params?.property_type && report.density_analysis && (
        <div className="space-y-2">
          <h3 className="section-pill">Financial Summary</h3>
          <div className="rounded-lg bg-[var(--bg-surface-raised)] p-4">
            <div className="mb-2 flex items-center gap-2">
              <span className="text-sm font-semibold text-[var(--text-secondary)]">
                {report.numeric_params.property_type === "land" && "Land / Development Site"}
                {report.numeric_params.property_type === "single_family" && "Single-Family Residential"}
                {report.numeric_params.property_type === "multifamily" && "Multifamily (2-4 Units)"}
                {report.numeric_params.property_type === "commercial_mf" && "Commercial Multifamily (5+ Units)"}
                {report.numeric_params.property_type === "commercial" && "Commercial"}
              </span>
              <span className="rounded-md bg-[var(--bg-surface-raised)] px-2 py-0.5 text-xs font-medium text-[var(--text-muted)] uppercase">
                {report.numeric_params.property_type}
              </span>
            </div>
            <div className="text-xs text-[var(--text-muted)] leading-relaxed">
              {report.numeric_params.property_type === "land" && (
                <p>Development potential: {report.density_analysis.max_units} units on {report.property_record?.lot_size_sqft?.toLocaleString() || "N/A"} sqft.</p>
              )}
              {report.numeric_params.property_type === "single_family" && (
                <p>Single-family lot. Provide purchase price and ARV for ROI analysis.</p>
              )}
              {report.numeric_params.property_type === "multifamily" && (
                <p>Small multifamily ({report.density_analysis.max_units} units max). Provide rent/unit for NOI and cap rate.</p>
              )}
              {report.numeric_params.property_type === "commercial_mf" && (
                <p>Commercial multifamily ({report.density_analysis.max_units} units max). Valued via income approach (NOI / Cap Rate).</p>
              )}
              {report.numeric_params.property_type === "commercial" && (
                <p>Commercial site. Max GLA: {report.density_analysis.max_gla_sqft?.toLocaleString() || "N/A"} sqft. Parking at {report.numeric_params.parking_per_1000_gla_sqft || "N/A"} per 1,000 SF.</p>
              )}
            </div>
          </div>
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

      {/* 3D Building View — all property types with lot dimensions */}
      {(() => {
        const np = report.numeric_params;
        const da = report.density_analysis;
        const maxHeight = np?.max_height_ft || 35;
        const lotSize = da?.lot_size_sqft || report.property_record?.lot_size_sqft || 0;
        if (lotWidth > 0 && lotDepth > 0) {
          return (
            <CollapsibleSection title="3D Building View" defaultOpen={true}>
              <EnvelopeViewerWrapper
                lotWidthFt={lotWidth}
                lotDepthFt={lotDepth}
                setbackFrontFt={setbackFront}
                setbackSideFt={setbackSide}
                setbackRearFt={setbackRear}
                maxHeightFt={maxHeight}
                buildableAreaSqft={da?.buildable_area_sqft ?? undefined}
                maxStories={np?.max_stories ?? undefined}
                maxLotCoveragePct={np?.max_lot_coverage_pct ?? undefined}
                far={np?.far ?? undefined}
                lotSizeSqft={lotSize || undefined}
                propertyType={np?.property_type ?? undefined}
                maxUnits={da?.max_units ?? undefined}
                parkingPerUnit={np?.parking_spaces_per_unit ?? undefined}
              />
            </CollapsibleSection>
          );
        }
        return null;
      })()}

      {/* Floor Plan — all property types with buildable dimensions */}
      {(() => {
        const da = report.density_analysis;
        const np = report.numeric_params;
        const buildW = Math.max(0, lotWidth - 2 * setbackSide);
        const buildD = Math.max(0, lotDepth - setbackFront - setbackRear);
        const maxHeight = np?.max_height_ft || 35;
        const lotSize = da?.lot_size_sqft || report.property_record?.lot_size_sqft || 0;
        if (buildW <= 0 || buildD <= 0) return null;
        return (
          <CollapsibleSection title="Floor Plan" defaultOpen={false}>
            <FloorPlanViewer
              buildableWidthFt={buildW}
              buildableDepthFt={buildD}
              maxHeightFt={maxHeight}
              maxStories={np?.max_stories || 2}
              maxLotCoveragePct={np?.max_lot_coverage_pct || 100}
              far={np?.far || 0}
              maxUnits={da?.max_units || 1}
              minUnitSizeSqft={np?.min_unit_size_sqft || 400}
              parkingPerUnit={np?.parking_spaces_per_unit || 2}
              lotSizeSqft={lotSize}
              propertyType={np?.property_type || "single_family"}
              zoningDistrict={report.zoning_district}
            />
          </CollapsibleSection>
        );
      })()}

      {/* Development Summary — compact stats for all property types */}
      {(() => {
        const buildW = lotWidth > 0 ? Math.max(0, lotWidth - 2 * setbackSide) : 0;
        const buildD = lotDepth > 0 ? Math.max(0, lotDepth - setbackFront - setbackRear) : 0;
        const footprint = buildW > 0 && buildD > 0 ? buildW * buildD : 0;
        const maxHeight = report.numeric_params?.max_height_ft || 35;
        const maxStories = report.numeric_params?.max_stories || null;
        const lotCoverage = report.numeric_params?.max_lot_coverage_pct || null;
        const lotSize = report.density_analysis?.lot_size_sqft || report.property_record?.lot_size_sqft || 0;
        const buildingArea = report.property_record?.building_area_sqft || 0;
        const coverageUsed = lotSize > 0 && buildingArea > 0 ? ((buildingArea / lotSize) * 100).toFixed(1) : null;
        const isCommercial = report.numeric_params?.property_type === "commercial";

        if (!footprint && !maxStories && !lotCoverage) return null;

        return (
          <div className="space-y-2">
            <h3 className="section-pill">Development Summary</h3>
            <div className="rounded-lg bg-amber-50/50 border border-amber-200 p-4 space-y-3">
              <p className="text-sm font-medium text-[var(--text-secondary)]">
                {isCommercial
                  ? "Commercial development site"
                  : maxUnits >= 2
                    ? `Multifamily — up to ${maxUnits} units`
                    : "Single-family residential lot"}
              </p>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                {footprint > 0 && (
                  <div className="rounded-lg bg-[var(--bg-surface)] p-3">
                    <div className="text-xs uppercase tracking-wider text-[var(--text-muted)]">Buildable Footprint</div>
                    <div className="mt-1 text-sm font-semibold text-[var(--text-primary)]">{Math.round(footprint).toLocaleString()} sqft</div>
                  </div>
                )}
                <div className="rounded-lg bg-[var(--bg-surface)] p-3">
                  <div className="text-xs uppercase tracking-wider text-[var(--text-muted)]">Max Height</div>
                  <div className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
                    {maxHeight} ft{maxStories ? ` / ${maxStories} stories` : ""}
                  </div>
                </div>
                {lotCoverage && (
                  <div className="rounded-lg bg-[var(--bg-surface)] p-3">
                    <div className="text-xs uppercase tracking-wider text-[var(--text-muted)]">Max Lot Coverage</div>
                    <div className="mt-1 text-sm font-semibold text-[var(--text-primary)]">{lotCoverage}%</div>
                  </div>
                )}
                {coverageUsed && (
                  <div className="rounded-lg bg-[var(--bg-surface)] p-3">
                    <div className="text-xs uppercase tracking-wider text-[var(--text-muted)]">Current Coverage</div>
                    <div className="mt-1 text-sm font-semibold text-[var(--text-primary)]">{coverageUsed}%</div>
                  </div>
                )}
              </div>
            </div>
          </div>
        );
      })()}

      {/* Property Intelligence — collapsible, default collapsed */}
      <CollapsibleSection title="Property Intelligence" defaultOpen={false}>
        <PropertyIntelligence report={report} />
      </CollapsibleSection>

      {/* Permitted Uses — collapsible, default collapsed */}
      <CollapsibleSection title="Permitted Uses" defaultOpen={false}>
        <div className="space-y-3">
          <UsesList title="Allowed" uses={report.allowed_uses} color="green" />
          <UsesList title="Conditional" uses={report.conditional_uses} color="yellow" />
          <UsesList title="Prohibited" uses={report.prohibited_uses} color="red" />
        </div>
      </CollapsibleSection>

      {/* Property Record — collapsible, default collapsed */}
      {report.property_record && (
        <CollapsibleSection title="Property Record" defaultOpen={false}>
          <PropertyCard record={report.property_record} />
        </CollapsibleSection>
      )}

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
