"use client";

import { useState, useCallback } from "react";
import dynamic from "next/dynamic";
import { ZoningReportData } from "@/lib/api";

const ArcGISParcelMap = dynamic(() => import("./ArcGISParcelMap"), {
  ssr: false,
  loading: () => (
    <div className="flex h-full min-h-[220px] items-center justify-center bg-[var(--bg-surface-raised)]">
      <div className="h-6 w-6 animate-spin rounded-full border-2 border-[var(--text-muted)] border-t-transparent" />
    </div>
  ),
});

interface ParcelViewerProps {
  report: ZoningReportData;
}

const MAPS_KEY = process.env.NEXT_PUBLIC_GOOGLE_MAPS_KEY || "";

type ViewTab = "street" | "parcel";

function formatCurrency(value: number | null | undefined): string {
  if (!value) return "";
  return `$${value.toLocaleString()}`;
}

function formatDate(raw: string): string {
  if (/^\d{8}$/.test(raw)) {
    const firstFour = parseInt(raw.slice(0, 4), 10);
    const isoStr = firstFour > 1900 && firstFour < 2100
      ? `${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)}` // YYYYMMDD
      : `${raw.slice(4, 8)}-${raw.slice(0, 2)}-${raw.slice(2, 4)}`; // MMDDYYYY
    const d = new Date(isoStr);
    if (!isNaN(d.getTime())) return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  }
  const d = new Date(raw);
  return isNaN(d.getTime()) ? raw : d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function MetricCell({ label, value }: { label: string; value: string | number | null | undefined }) {
  if (!value && value !== 0) return null;
  const display = typeof value === "number"
    ? (/year/i.test(label) ? value.toString() : value.toLocaleString())
    : value;
  return (
    <div className="rounded-lg bg-[var(--bg-surface-raised)] p-2.5">
      <div className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-muted)]">{label}</div>
      <div className="mt-0.5 text-sm font-semibold text-[var(--text-primary)]">{display}</div>
    </div>
  );
}

function PropertyDetails({ report, floodZone }: { report: ZoningReportData; floodZone?: { zone: string; sfha: boolean } | null }) {
  const pr = report.property_record!;

  return (
    <div className="flex h-full flex-col gap-4 p-4 sm:p-5 lg:p-6">
      {/* Header badges */}
      <div className="flex flex-wrap items-center gap-2">
        {pr.folio && (
          <span className="rounded-md bg-[var(--bg-surface-raised)] px-2 py-0.5 text-xs font-medium text-[var(--text-secondary)]">
            {pr.folio}
          </span>
        )}
        <span className="rounded-md bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-400">
          {report.zoning_district}
        </span>
      </div>

      {/* Address */}
      <div>
        <h3 className="text-sm font-semibold text-[var(--text-primary)] sm:text-base">
          {pr.address || report.formatted_address}
        </h3>
        <p className="mt-0.5 text-xs text-[var(--text-muted)]">
          {report.municipality}, {report.county} County
        </p>
      </div>

      {/* Owner */}
      {pr.owner && (
        <div className="text-xs text-[var(--text-muted)]">
          <span className="font-medium text-[var(--text-secondary)]">Owner:</span> {pr.owner}
        </div>
      )}

      {/* Key metrics grid */}
      <div className="grid grid-cols-2 gap-2">
        <MetricCell label="Lot Size" value={pr.lot_size_sqft ? `${pr.lot_size_sqft.toLocaleString()} sf` : null} />
        <MetricCell label="Lot Dims" value={pr.lot_dimensions || null} />
        {floodZone && (
          <MetricCell label="Flood Zone" value={`${floodZone.zone} (${floodZone.sfha ? "SFHA" : "Minimal risk"})`} />
        )}
        <MetricCell label="Year Built" value={pr.year_built || null} />
        <MetricCell label="Living Area" value={pr.living_area_sqft ? `${pr.living_area_sqft.toLocaleString()} sf` : null} />
      </div>

      {/* Valuation row */}
      {(pr.assessed_value || pr.market_value || pr.last_sale_price) && (
        <div className="space-y-1.5 border-t border-[var(--border)] pt-3">
          <div className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-muted)]">Valuation</div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
            {pr.assessed_value > 0 && (
              <div>
                <span className="text-[var(--text-muted)]">Assessed: </span>
                <span className="font-semibold text-[var(--text-primary)]">{formatCurrency(pr.assessed_value)}</span>
              </div>
            )}
            {pr.market_value > 0 && (
              <div>
                <span className="text-[var(--text-muted)]">Market: </span>
                <span className="font-semibold text-[var(--text-primary)]">{formatCurrency(pr.market_value)}</span>
              </div>
            )}
            {pr.last_sale_price > 0 && (
              <div>
                <span className="text-[var(--text-muted)]">Last Sale: </span>
                <span className="font-semibold text-[var(--text-primary)]">{formatCurrency(pr.last_sale_price)}</span>
                {pr.last_sale_date && (
                  <span className="ml-1 text-[var(--text-muted)]">({formatDate(pr.last_sale_date)})</span>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function TabBar({ activeTab, onTabChange }: { activeTab: ViewTab; onTabChange: (tab: ViewTab) => void }) {
  const tabs: { id: ViewTab; label: string; icon: React.ReactNode }[] = [
    {
      id: "street",
      label: "Street View",
      icon: (
        <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25" />
        </svg>
      ),
    },
    {
      id: "parcel",
      label: "Parcel Map",
      icon: (
        <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 6.75V15m6-6v8.25m.503 3.498l4.875-2.437c.381-.19.622-.58.622-1.006V4.82c0-.836-.88-1.38-1.628-1.006l-3.869 1.934c-.317.159-.69.159-1.006 0L9.503 3.252a1.125 1.125 0 00-1.006 0L3.622 5.689C3.24 5.88 3 6.27 3 6.695V19.18c0 .836.88 1.38 1.628 1.006l3.869-1.934c.317-.159.69-.159 1.006 0l4.994 2.497c.317.158.69.158 1.006 0z" />
        </svg>
      ),
    },
  ];

  return (
    <div className="flex border-b border-[var(--border)]">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onTabChange(tab.id)}
          className={`flex items-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors ${
            activeTab === tab.id
              ? "border-b-2 border-[var(--text-primary)] text-[var(--text-primary)]"
              : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
          }`}
        >
          {tab.icon}
          {tab.label}
        </button>
      ))}
    </div>
  );
}

function StreetViewTab({ report }: { report: ZoningReportData }) {
  const [imgError, setImgError] = useState(false);
  const googleMapsUrl = `https://www.google.com/maps/@${report.lat},${report.lng},3a,75y,0h,90t/data=!3m1!1e1`;

  if (!MAPS_KEY || imgError) {
    return (
      <a
        href={googleMapsUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="flex h-full min-h-[220px] items-center justify-center rounded-b-xl bg-[var(--bg-surface-raised)] transition-colors hover:bg-[var(--bg-surface-raised)]/80 lg:rounded-bl-none lg:rounded-r-xl"
      >
        <div className="text-center">
          <svg className="mx-auto h-8 w-8 text-[var(--text-muted)]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
            <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 12l8.954-8.955c.44-.439 1.152-.439 1.591 0L21.75 12M4.5 9.75v10.125c0 .621.504 1.125 1.125 1.125H9.75v-4.875c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21h4.125c.621 0 1.125-.504 1.125-1.125V9.75M8.25 21h8.25" />
          </svg>
          <p className="mt-2 text-xs text-[var(--text-muted)]">View on Google Maps ↗</p>
        </div>
      </a>
    );
  }

  const staticUrl =
    `https://maps.googleapis.com/maps/api/streetview` +
    `?size=640x400&location=${report.lat},${report.lng}` +
    `&fov=80&heading=0&pitch=5&key=${MAPS_KEY}`;

  return (
    <div className="relative h-full min-h-[220px] overflow-hidden rounded-b-xl lg:rounded-bl-none lg:rounded-r-xl">
      <img
        src={staticUrl}
        alt={`Street view of ${report.formatted_address}`}
        className="h-full w-full object-cover"
        onError={() => setImgError(true)}
      />
      <div className="absolute bottom-0 left-0 right-0 flex items-center justify-between bg-[var(--bg-surface)]/90 px-3 py-1.5 backdrop-blur-sm">
        <span className="text-xs text-[var(--text-muted)]">Google Street View</span>
        <a
          href={googleMapsUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs font-medium text-emerald-600 hover:text-emerald-500 dark:text-emerald-400 dark:hover:text-emerald-300"
        >
          Open full view
        </a>
      </div>
    </div>
  );
}

function ParcelMapTab({ report, onFloodZone }: { report: ZoningReportData; onFloodZone?: (zone: string, sfha: boolean) => void }) {
  return (
    <div className="h-full min-h-[220px] overflow-hidden rounded-b-xl lg:rounded-bl-none lg:rounded-r-xl">
      <ArcGISParcelMap
        lat={report.lat!}
        lng={report.lng!}
        county={report.county}
        parcelGeometry={report.property_record?.parcel_geometry}
        lotDimensions={report.property_record?.lot_dimensions}
        lotSizeSqft={report.property_record?.lot_size_sqft}
        zoningLayerUrl={report.property_record?.zoning_layer_url}
        onFloodZone={onFloodZone}
      />
    </div>
  );
}

export default function ParcelViewer({ report }: ParcelViewerProps) {
  const [activeTab, setActiveTab] = useState<ViewTab>("street");
  const [floodZone, setFloodZone] = useState<{ zone: string; sfha: boolean } | null>(null);
  const hasCoords = report.lat != null && report.lng != null;

  const handleFloodZone = useCallback((zone: string, sfha: boolean) => {
    setFloodZone({ zone, sfha });
  }, []);

  if (!report.property_record) return null;

  return (
    <div className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)]">
      {/* Section label */}
      <div className="border-b border-[var(--border)] px-4 py-2.5 sm:px-5">
        <span className="section-pill">Parcel Viewer</span>
      </div>

      {hasCoords ? (
        /* Split panel: details left, tabbed views right */
        <div className="flex flex-col lg:flex-row">
          {/* Left: Property details — 40% on desktop */}
          <div className="order-2 lg:order-1 lg:w-[40%] lg:border-r lg:border-[var(--border)]">
            <PropertyDetails report={report} floodZone={floodZone} />
          </div>

          {/* Right: Tabbed views — 60% on desktop */}
          <div className="order-1 flex flex-col lg:order-2 lg:w-[60%]">
            <TabBar activeTab={activeTab} onTabChange={setActiveTab} />
            <div className="flex-1 lg:min-h-[380px]">
              {activeTab === "street" && <StreetViewTab report={report} />}
              {activeTab === "parcel" && <ParcelMapTab report={report} onFloodZone={handleFloodZone} />}
            </div>
          </div>
        </div>
      ) : (
        /* No coordinates — full-width property details only */
        <PropertyDetails report={report} />
      )}
    </div>
  );
}
