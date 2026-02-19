"use client";

import { ZoningReportData } from "@/lib/api";
import DensityBreakdown from "./DensityBreakdown";
import PropertyCard from "./PropertyCard";

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
  if (!value) return null;
  return (
    <div className="flex justify-between border-b border-stone-200 py-1.5">
      <span className="text-sm text-stone-500">{label}</span>
      <span className="text-sm font-medium text-stone-800">{value}</span>
    </div>
  );
}

function UsesList({ title, uses, color }: { title: string; uses: string[]; color: string }) {
  if (!uses.length) return null;
  const colors: Record<string, string> = {
    green: "bg-emerald-50 text-emerald-700",
    yellow: "bg-amber-50 text-amber-700",
    red: "bg-red-50 text-red-700",
  };
  return (
    <div>
      <h4 className="mb-1.5 text-xs font-medium text-stone-500">{title}</h4>
      <div className="flex flex-wrap gap-1.5">
        {uses.map((use, i) => (
          <span key={i} className={`rounded-md px-2 py-0.5 text-xs ${colors[color]}`}>
            {use}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function ZoningReport({ report }: ZoningReportProps) {
  return (
    <div className="w-full space-y-6 rounded-xl border border-stone-200 bg-white p-6 shadow-sm">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-xl font-bold text-stone-800">{report.formatted_address}</h2>
          <p className="mt-1 text-sm text-stone-500">
            {report.municipality}, {report.county} County
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <ConfidenceBadge level={report.confidence} />
          <div className="text-right">
            <div className="text-2xl font-bold text-amber-700">{report.zoning_district}</div>
            <div className="text-xs text-stone-500">{report.zoning_description}</div>
          </div>
        </div>
      </div>

      {/* Summary */}
      {report.summary && (
        <div className="rounded-lg bg-stone-50 p-4 text-sm leading-relaxed text-stone-600">
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
      {(report.setbacks.front || report.setbacks.side || report.setbacks.rear) && (
        <Section title="Setbacks">
          <div className="grid grid-cols-3 gap-3">
            {[
              { label: "Front", value: report.setbacks.front },
              { label: "Side", value: report.setbacks.side },
              { label: "Rear", value: report.setbacks.rear },
            ].map((s) => (
              <div key={s.label} className="rounded-lg bg-stone-50 p-3 text-center">
                <div className="text-xs text-stone-500">{s.label}</div>
                <div className="mt-1 text-lg font-semibold text-stone-800">{s.value || "N/A"}</div>
              </div>
            ))}
          </div>
        </Section>
      )}

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

      {/* Sources */}
      {report.sources.length > 0 && (
        <Section title="Sources">
          <div className="space-y-1">
            {report.sources.map((source, i) => (
              <div key={i} className="text-xs text-stone-500">
                {source}
              </div>
            ))}
          </div>
        </Section>
      )}

    </div>
  );
}
