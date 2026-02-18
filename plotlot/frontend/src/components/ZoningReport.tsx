"use client";

import { ZoningReportData } from "@/lib/api";
import DensityBreakdown from "./DensityBreakdown";
import PropertyCard from "./PropertyCard";

interface ZoningReportProps {
  report: ZoningReportData;
}

function ConfidenceBadge({ level }: { level: string }) {
  const colors: Record<string, string> = {
    high: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30",
    medium: "bg-amber-500/20 text-amber-400 border-amber-500/30",
    low: "bg-red-500/20 text-red-400 border-red-500/30",
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
      <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-400">{title}</h3>
      {children}
    </div>
  );
}

function DataRow({ label, value }: { label: string; value: string }) {
  if (!value) return null;
  return (
    <div className="flex justify-between border-b border-zinc-800/50 py-1.5">
      <span className="text-sm text-zinc-500">{label}</span>
      <span className="text-sm font-medium text-zinc-200">{value}</span>
    </div>
  );
}

function UsesList({ title, uses, color }: { title: string; uses: string[]; color: string }) {
  if (!uses.length) return null;
  const colors: Record<string, string> = {
    green: "bg-emerald-500/10 text-emerald-400",
    yellow: "bg-amber-500/10 text-amber-400",
    red: "bg-red-500/10 text-red-400",
  };
  return (
    <div>
      <h4 className="mb-1.5 text-xs font-medium text-zinc-500">{title}</h4>
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
    <div className="w-full space-y-6 rounded-xl border border-zinc-800 bg-zinc-900/50 p-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-xl font-bold text-white">{report.formatted_address}</h2>
          <p className="mt-1 text-sm text-zinc-400">
            {report.municipality}, {report.county} County
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          <ConfidenceBadge level={report.confidence} />
          <div className="text-right">
            <div className="text-2xl font-bold text-emerald-400">{report.zoning_district}</div>
            <div className="text-xs text-zinc-500">{report.zoning_description}</div>
          </div>
        </div>
      </div>

      {/* Summary */}
      {report.summary && (
        <div className="rounded-lg bg-zinc-800/30 p-4 text-sm leading-relaxed text-zinc-300">
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
              <div key={s.label} className="rounded-lg bg-zinc-800/30 p-3 text-center">
                <div className="text-xs text-zinc-500">{s.label}</div>
                <div className="mt-1 text-lg font-semibold text-zinc-200">{s.value || "N/A"}</div>
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
              <div key={i} className="text-xs text-zinc-600">
                {source}
              </div>
            ))}
          </div>
        </Section>
      )}

    </div>
  );
}
