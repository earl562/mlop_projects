"use client";

import { useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { ZoningReportData, SourceRefData } from "@/lib/api";
import { springGentle } from "@/lib/motion";
import type { DealType } from "./DealTypeSelector";
import DealHeroCard from "./DealHeroCard";
import ParcelViewer from "./ParcelViewer";
import DensityBreakdown from "./DensityBreakdown";
import BuildingRenderViewer from "./BuildingRenderViewer";
import DocumentGenerator from "./DocumentGenerator";
import FloorPlanViewer from "./FloorPlanViewer";
import SetbackDiagram from "./SetbackDiagram";
import PropertyIntelligence from "./PropertyIntelligence";
import { useToast } from "./Toast";
import ErrorBoundary from "./ErrorBoundary";
import {
  getCoverageLevel, CoverageBadge, ConfidenceBadge, CopyButton,
  DataRow, UsesList, parseNumericFt, estimateLotDimensions,
  ComparableSalesSection, ProFormaSection,
} from "./ReportShared";

type ReportTab = "property" | "zoning" | "analysis" | "deal";

interface TabbedReportProps {
  report: ZoningReportData;
  dealType: DealType;
}


const TABS: { id: ReportTab; label: string; icon: React.ReactNode }[] = [
  {
    id: "property",
    label: "Property",
    icon: (
      <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25" />
      </svg>
    ),
  },
  {
    id: "zoning",
    label: "Zoning",
    icon: (
      <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 6.75V15m6-6v8.25m.503 3.498l4.875-2.437c.381-.19.622-.58.622-1.006V4.82c0-.836-.88-1.38-1.628-1.006l-3.869 1.934c-.317.159-.69.159-1.006 0L9.503 3.252a1.125 1.125 0 00-1.006 0L3.622 5.689C3.24 5.88 3 6.27 3 6.695V19.18c0 .836.88 1.38 1.628 1.006l3.869-1.934c.317-.159.69-.159 1.006 0l4.994 2.497c.317.158.69.158 1.006 0z" />
      </svg>
    ),
  },
  {
    id: "analysis",
    label: "Analysis",
    icon: (
      <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
      </svg>
    ),
  },
  {
    id: "deal",
    label: "Deal",
    icon: (
      <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
        <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v12m-3-2.818l.879.659c1.171.879 3.07.879 4.242 0 1.172-.879 1.172-2.303 0-3.182C13.536 12.219 12.768 12 12 12c-.725 0-1.45-.22-2.003-.659-1.106-.879-1.106-2.303 0-3.182s2.9-.879 4.006 0l.415.33M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
  },
];

// Deal-type-specific tab visibility
const DEAL_TABS: Record<DealType, ReportTab[]> = {
  land_deal: ["property", "zoning", "analysis", "deal"],
  wholesale: ["property", "zoning", "deal"],
  creative_finance: ["property", "deal"],
  hybrid: ["property", "zoning", "analysis", "deal"],
};

export default function TabbedReport({ report, dealType }: TabbedReportProps) {
  const visibleTabIds = DEAL_TABS[dealType] || DEAL_TABS.land_deal;
  const visibleTabs = TABS.filter((t) => visibleTabIds.includes(t.id));
  const [activeTab, setActiveTab] = useState<ReportTab>(visibleTabIds[0]);
  const [sourcesOpen, setSourcesOpen] = useState(false);
  const [pdfLoading, setPdfLoading] = useState(false);
  const { toast } = useToast();

  const setbackFront = report.numeric_params?.setback_front_ft || parseNumericFt(report.setbacks?.front);
  const setbackSide = report.numeric_params?.setback_side_ft || parseNumericFt(report.setbacks?.side);
  const setbackRear = report.numeric_params?.setback_rear_ft || parseNumericFt(report.setbacks?.rear);
  const { lotWidth, lotDepth } = estimateLotDimensions(report);

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
      toast("PDF download failed — please try again");
    } finally {
      setPdfLoading(false);
    }
  }, [report, pdfLoading, toast]);

  return (
    <div
      className="w-full space-y-0 rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)] sm:rounded-3xl"
      style={{ boxShadow: "var(--shadow-card)" }}
      data-testid="report-root"
    >
      {/* Header */}
      <div className="space-y-4 p-5 sm:p-8">
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
              <CoverageBadge municipality={report.municipality} />
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2">
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

        {/* Hero card — deal-type-specific */}
        <DealHeroCard report={report} dealType={dealType} />
      </div>

      {/* Tab bar */}
      <div className="flex border-b border-t border-[var(--border)]" role="tablist" aria-label="Report sections">
        {visibleTabs.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            id={`report-${tab.id}-tab`}
            aria-selected={activeTab === tab.id}
            aria-controls={`report-section-${tab.id}`}
            onClick={() => setActiveTab(tab.id)}
            data-testid={`report-${tab.id}-tab`}
            className={`flex flex-1 items-center justify-center gap-1.5 px-3 py-3 text-xs font-medium transition-colors -mb-px sm:text-sm ${
              activeTab === tab.id
                ? "border-b-2 border-amber-500 text-[var(--text-primary)]"
                : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
            }`}
          >
            {tab.icon}
            <span className="sr-only sm:not-sr-only sm:inline">{tab.label}</span>
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="p-5 sm:p-8" role="tabpanel" id={`report-section-${activeTab}`} aria-labelledby={`report-${activeTab}-tab`}>
        <AnimatePresence mode="wait">
        {/* Property Tab */}
        {activeTab === "property" && (
          <motion.div key="property" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={springGentle} className="space-y-6" data-testid="report-section-property">
            {report.property_record && <ErrorBoundary><ParcelViewer report={report} /></ErrorBoundary>}

            {/* Zoning district quick info */}
            <div className="flex flex-wrap items-center gap-3">
              <span className="font-display text-3xl text-[var(--text-primary)] sm:text-4xl">{report.zoning_district}</span>
              <CopyButton text={report.zoning_district} />
              <span className="text-sm text-[var(--text-muted)]">{report.zoning_description}</span>
            </div>
          </motion.div>
        )}

        {/* Zoning Tab */}
        {activeTab === "zoning" && (
          <motion.div key="zoning" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={springGentle} className="space-y-6" data-testid="report-section-zoning">
            {/* Partial coverage callout */}
            {getCoverageLevel(report.municipality) === "partial" && !report.zoning_district && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800 dark:border-amber-800 dark:bg-amber-950/20 dark:text-amber-300">
                Zoning ordinance data isn&apos;t indexed for {report.municipality} yet.
                Property record and comparable sales data are still available.
              </div>
            )}
            {/* Dimensional Standards */}
            <div className="space-y-1">
              <h3 className="text-xs font-medium uppercase tracking-wider text-[var(--text-muted)]">
                Dimensional Standards
                {report.source_refs && report.source_refs.length > 0 && (
                  <span className="ml-2 text-[9px] font-normal normal-case text-blue-500">
                    {report.source_refs.length} source{report.source_refs.length !== 1 ? "s" : ""}
                  </span>
                )}
              </h3>
              <DataRow label="Max Height" value={report.max_height} citation={report.source_refs?.[0] ? { ...report.source_refs[0], index: 0 } : undefined} />
              <DataRow label="Max Density" value={report.max_density} citation={report.source_refs?.[1] ? { ...report.source_refs[1], index: 1 } : undefined} />
              <DataRow label="Floor Area Ratio" value={report.floor_area_ratio} citation={report.source_refs?.[2] ? { ...report.source_refs[2], index: 2 } : undefined} />
              <DataRow label="Lot Coverage" value={report.lot_coverage} citation={report.source_refs?.[3] ? { ...report.source_refs[3], index: 3 } : undefined} />
              <DataRow label="Min Lot Size" value={report.min_lot_size} citation={report.source_refs?.[4] ? { ...report.source_refs[4], index: 4 } : undefined} />
              <DataRow label="Parking" value={report.parking_requirements} />
            </div>

            {/* Setbacks */}
            {report.setbacks && [report.setbacks.front, report.setbacks.side, report.setbacks.rear].some((v) => v && v !== "null") && (
              <div className="space-y-3">
                <h3 className="text-xs font-medium uppercase tracking-wider text-[var(--text-muted)]">Setbacks</h3>
                {lotWidth > 0 && lotDepth > 0 && (setbackFront > 0 || setbackSide > 0 || setbackRear > 0) && (
                  <ErrorBoundary><SetbackDiagram lotWidth={lotWidth} lotDepth={lotDepth} setbackFront={setbackFront} setbackSide={setbackSide} setbackRear={setbackRear} /></ErrorBoundary>
                )}
                <div className="grid grid-cols-3 gap-3">
                  {[
                    { label: "Front", value: report.setbacks.front },
                    { label: "Side", value: report.setbacks.side },
                    { label: "Rear", value: report.setbacks.rear },
                  ].map((s) => (
                    <div key={s.label} className="rounded-lg bg-[var(--bg-surface-raised)] p-2 text-center sm:p-3">
                      <div className="text-xs text-[var(--text-muted)]">{s.label}</div>
                      <div className="mt-1 text-base font-semibold text-[var(--text-primary)] sm:text-lg">
                        {s.value && s.value !== "null" ? s.value : "N/A"}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Permitted Uses */}
            <div className="space-y-3">
              <h3 className="text-xs font-medium uppercase tracking-wider text-[var(--text-muted)]">Permitted Uses</h3>
              <UsesList title="Allowed" uses={report.allowed_uses} color="green" />
              <UsesList title="Conditional" uses={report.conditional_uses} color="yellow" />
              <UsesList title="Prohibited" uses={report.prohibited_uses} color="red" />
            </div>

            {/* Sources */}
            {report.sources.length > 0 && (
              <div className="space-y-2">
                <button onClick={() => setSourcesOpen(!sourcesOpen)} className="flex items-center gap-2 text-xs text-[var(--text-muted)] hover:text-[var(--text-secondary)]">
                  <span>View {report.sources.length} source{report.sources.length !== 1 ? "s" : ""}</span>
                  <svg className={`h-3 w-3 transition-transform ${sourcesOpen ? "rotate-90" : ""}`} viewBox="0 0 20 20" fill="currentColor">
                    <path fillRule="evenodd" d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z" clipRule="evenodd" />
                  </svg>
                </button>
                {sourcesOpen && (
                  <div className="space-y-1 animate-fade-in">
                    {report.sources.map((source, i) => (
                      <div key={i} className="text-xs text-[var(--text-muted)]">{source}</div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </motion.div>
        )}

        {/* Analysis Tab */}
        {activeTab === "analysis" && (
          <motion.div key="analysis" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={springGentle} className="space-y-6" data-testid="report-section-analysis">
            {/* Density Breakdown */}
            {report.density_analysis && (() => {
              const buildW = lotWidth > 0 ? Math.max(0, lotWidth - 2 * setbackSide) : 0;
              const buildD = lotDepth > 0 ? Math.max(0, lotDepth - setbackFront - setbackRear) : 0;
              const footprint = buildW > 0 && buildD > 0 ? buildW * buildD : 0;
              const lotSize = report.density_analysis.lot_size_sqft || report.property_record?.lot_size_sqft || 0;
              const buildingArea = report.property_record?.building_area_sqft || 0;
              const coverageUsed = lotSize > 0 && buildingArea > 0 ? ((buildingArea / lotSize) * 100).toFixed(1) : null;
              return <ErrorBoundary><DensityBreakdown analysis={report.density_analysis} buildableFootprintSqft={footprint > 0 ? footprint : undefined} currentCoveragePct={coverageUsed} /></ErrorBoundary>;
            })()}

            {/* Floor Plan */}
            {(() => {
              const np = report.numeric_params;
              const da = report.density_analysis;
              const buildW = Math.max(0, lotWidth - 2 * setbackSide);
              const buildD = Math.max(0, lotDepth - setbackFront - setbackRear);
              const lotSize = da?.lot_size_sqft || report.property_record?.lot_size_sqft || 0;
              if (buildW <= 0 || buildD <= 0) return null;
              return (
                <div className="space-y-2">
                  <h3 className="text-xs font-medium uppercase tracking-wider text-[var(--text-muted)]">Floor Plan</h3>
                  <ErrorBoundary><FloorPlanViewer
                    buildableWidthFt={buildW}
                    buildableDepthFt={buildD}
                    maxHeightFt={np?.max_height_ft || 35}
                    maxStories={np?.max_stories || 2}
                    maxLotCoveragePct={np?.max_lot_coverage_pct || 100}
                    far={np?.far || 0}
                    maxUnits={da?.max_units || 1}
                    minUnitSizeSqft={np?.min_unit_size_sqft || 400}
                    parkingPerUnit={np?.parking_spaces_per_unit || 2}
                    lotSizeSqft={lotSize}
                    propertyType={np?.property_type || "single_family"}
                    zoningDistrict={report.zoning_district}
                  /></ErrorBoundary>
                </div>
              );
            })()}

            {/* AI Architectural Render */}
            {lotWidth > 0 && lotDepth > 0 && (
              <div className="space-y-2">
                <h3 className="text-xs font-medium uppercase tracking-wider text-[var(--text-muted)]">AI Architectural Render</h3>
                <ErrorBoundary><BuildingRenderViewer
                  lotWidthFt={lotWidth}
                  lotDepthFt={lotDepth}
                  setbackFrontFt={setbackFront}
                  setbackSideFt={setbackSide}
                  setbackRearFt={setbackRear}
                  maxHeightFt={report.numeric_params?.max_height_ft || 35}
                  maxStories={report.numeric_params?.max_stories ?? undefined}
                  propertyType={report.numeric_params?.property_type ?? undefined}
                  maxUnits={report.density_analysis?.max_units ?? undefined}
                  zoningDistrict={report.zoning_district}
                  municipality={report.municipality}
                /></ErrorBoundary>
              </div>
            )}

            {/* Property Intelligence */}
            <div className="space-y-2">
              <h3 className="text-xs font-medium uppercase tracking-wider text-[var(--text-muted)]">Property Intelligence</h3>
              <PropertyIntelligence report={report} />
            </div>
          </motion.div>
        )}

        {/* Deal Tab */}
        {activeTab === "deal" && (
          <motion.div key="deal" initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={springGentle} className="space-y-6" data-testid="report-section-deal">
            {/* Comparable Sales */}
            {(report.comp_analysis?.comparables?.length ?? 0) > 0 && (
              <div className="space-y-3">
                <h3 className="text-xs font-medium uppercase tracking-wider text-[var(--text-muted)]">Comparable Sales</h3>
                <ComparableSalesSection report={report} />
              </div>
            )}

            {/* Land Pro Forma */}
            {report.pro_forma && report.pro_forma.max_land_price > 0 && (
              <div className="space-y-3">
                <h3 className="text-xs font-medium uppercase tracking-wider text-[var(--text-muted)]">Land Pro Forma</h3>
                <ProFormaSection report={report} />
              </div>
            )}

            {/* Document Generation */}
            <div className="space-y-2">
              <h3 className="text-xs font-medium uppercase tracking-wider text-[var(--text-muted)]">Generate Documents</h3>
              <DocumentGenerator report={report} />
            </div>
          </motion.div>
        )}
        </AnimatePresence>
      </div>
    </div>
  );
}
