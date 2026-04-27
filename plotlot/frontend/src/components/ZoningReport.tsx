"use client";

import { useState, useCallback } from "react";
import { ZoningReportData } from "@/lib/api";
import DensityBreakdown from "./DensityBreakdown";
import DocumentGenerator from "./DocumentGenerator";
import ParcelViewer from "./ParcelViewer";
import SetbackDiagram from "./SetbackDiagram";
import ErrorBoundary from "./ErrorBoundary";
import {
  getCoverageLevel, CoverageBadge, ConfidenceBadge, CopyButton,
  DataRow, UsesList, parseNumericFt, estimateLotDimensions,
  ComparableSalesSection, ProFormaSection,
} from "./ReportShared";

interface ZoningReportProps {
  report: ZoningReportData;
}

function CollapsibleSection({ title, defaultOpen = true, children }: { title: string; defaultOpen?: boolean; children: React.ReactNode }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="space-y-3">
      <button onClick={() => setOpen(!open)} className="flex items-center gap-2 text-left active:scale-[0.98]">
        <span className="section-pill">{title}</span>
        <svg className={`h-3 w-3 text-[var(--text-muted)] transition-transform duration-200 ${open ? "rotate-90" : ""}`} viewBox="0 0 20 20" fill="currentColor">
          <path fillRule="evenodd" d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z" clipRule="evenodd" />
        </svg>
      </button>
      {open && <div className="animate-fade-in">{children}</div>}
    </div>
  );
}

export default function ZoningReport({ report }: ZoningReportProps) {
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [pdfError, setPdfError] = useState<string | null>(null);

  const { lotWidth, lotDepth } = estimateLotDimensions(report);
  const setbackFront = report.numeric_params?.setback_front_ft || parseNumericFt(report.setbacks?.front);
  const setbackSide = report.numeric_params?.setback_side_ft || parseNumericFt(report.setbacks?.side);
  const setbackRear = report.numeric_params?.setback_rear_ft || parseNumericFt(report.setbacks?.rear);

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
          <p className="mt-1 text-xs text-[var(--text-muted)] sm:text-sm">{report.municipality}, {report.county} County</p>
          <div className="mt-2"><CoverageBadge municipality={report.municipality} /></div>
        </div>
        <div className="flex shrink-0 flex-col items-end gap-2">
          <ConfidenceBadge level={report.confidence} />
          {pdfError && <p className="text-right text-[10px] text-red-500">{pdfError}</p>}
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

      {report.property_record && <ErrorBoundary><ParcelViewer report={report} /></ErrorBoundary>}

      <div className="flex flex-wrap items-center gap-3 sm:gap-4">
        <span className="font-display text-3xl text-[var(--text-primary)] sm:text-4xl">{report.zoning_district}</span>
        <CopyButton text={report.zoning_district} />
        <span className="text-sm text-[var(--text-muted)]">{report.zoning_description}</span>
      </div>

      {getCoverageLevel(report.municipality) === "partial" && !report.zoning_district && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/20 dark:text-amber-300">
          Zoning ordinance data isn&apos;t indexed for {report.municipality} yet.
          Property record and comparable sales data are still available.
        </div>
      )}

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

      {report.density_analysis && (() => {
        const buildW = lotWidth > 0 ? Math.max(0, lotWidth - 2 * setbackSide) : 0;
        const buildD = lotDepth > 0 ? Math.max(0, lotDepth - setbackFront - setbackRear) : 0;
        const footprint = buildW > 0 && buildD > 0 ? buildW * buildD : 0;
        const lotSize = report.density_analysis.lot_size_sqft || report.property_record?.lot_size_sqft || 0;
        const buildingArea = report.property_record?.building_area_sqft || 0;
        const coverageUsed = lotSize > 0 && buildingArea > 0 ? ((buildingArea / lotSize) * 100).toFixed(1) : null;
        return (
          <ErrorBoundary>
            <DensityBreakdown analysis={report.density_analysis} buildableFootprintSqft={footprint > 0 ? footprint : undefined} currentCoveragePct={coverageUsed} />
          </ErrorBoundary>
        );
      })()}

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

      <CollapsibleSection title="Dimensional Standards">
        <div className="space-y-1">
          <DataRow label="Max Height" value={report.max_height} />
          <DataRow label="Max Density" value={report.max_density} />
          <DataRow label="Floor Area Ratio" value={report.floor_area_ratio} />
          <DataRow label="Lot Coverage" value={report.lot_coverage} />
          <DataRow label="Min Lot Size" value={report.min_lot_size} />
          <DataRow label="Parking" value={report.parking_requirements} />
        </div>
      </CollapsibleSection>

      {report.setbacks && [report.setbacks.front, report.setbacks.side, report.setbacks.rear].some((v) => v && v !== "null") && (
        <CollapsibleSection title="Setbacks">
          {lotWidth > 0 && lotDepth > 0 && (setbackFront > 0 || setbackSide > 0 || setbackRear > 0) && (
            <ErrorBoundary>
              <SetbackDiagram lotWidth={lotWidth} lotDepth={lotDepth} setbackFront={setbackFront} setbackSide={setbackSide} setbackRear={setbackRear} />
            </ErrorBoundary>
          )}
          <div className="grid grid-cols-3 gap-3">
            {[
              { label: "Front", value: report.setbacks.front },
              { label: "Side", value: report.setbacks.side },
              { label: "Rear", value: report.setbacks.rear },
            ].map((s) => (
              <div key={s.label} className="rounded-lg bg-[var(--bg-surface-raised)] p-2 text-center shadow-[inset_0_1px_3px_rgba(0,0,0,0.06)] sm:p-3">
                <div className="text-xs text-[var(--text-muted)]">{s.label}</div>
                <div className="mt-1 text-base font-semibold text-[var(--text-primary)] sm:text-lg">
                  {s.value && s.value !== "null" ? s.value : "N/A"}
                </div>
              </div>
            ))}
          </div>
        </CollapsibleSection>
      )}

      <CollapsibleSection title="Permitted Uses" defaultOpen={false}>
        <div className="space-y-3">
          <UsesList title="Allowed" uses={report.allowed_uses} color="green" />
          <UsesList title="Conditional" uses={report.conditional_uses} color="yellow" />
          <UsesList title="Prohibited" uses={report.prohibited_uses} color="red" />
        </div>
      </CollapsibleSection>

      {(report.comp_analysis?.comparables?.length ?? 0) > 0 && (
        <CollapsibleSection title="Comparable Sales">
          <ComparableSalesSection report={report} />
        </CollapsibleSection>
      )}

      {report.pro_forma && report.pro_forma.max_land_price > 0 && (
        <CollapsibleSection title="Land Pro Forma">
          <ProFormaSection report={report} />
        </CollapsibleSection>
      )}

      <CollapsibleSection title="Generate Documents" defaultOpen={!!report.pro_forma}>
        <DocumentGenerator report={report} />
      </CollapsibleSection>

      {report.sources.length > 0 && (
        <div className="space-y-2">
          <button onClick={() => setSourcesOpen(!sourcesOpen)} className="flex min-h-[44px] items-center gap-2 active:scale-[0.98]">
            <span className="section-pill">View {report.sources.length} source{report.sources.length !== 1 ? "s" : ""}</span>
            <svg className={`h-3 w-3 text-[var(--text-muted)] transition-transform ${sourcesOpen ? "rotate-90" : ""}`} viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z" clipRule="evenodd" />
            </svg>
          </button>
          {sourcesOpen && (
            <div className="space-y-1 animate-fade-in">
              {report.sources.map((source, i) => <div key={i} className="text-xs text-[var(--text-muted)]">{source}</div>)}
            </div>
          )}
        </div>
      )}

      <div className="flex items-center justify-end gap-3 border-t border-[var(--border)] pt-6">
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
