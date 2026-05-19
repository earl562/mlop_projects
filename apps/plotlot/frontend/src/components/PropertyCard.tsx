"use client";

import { PropertyRecordData } from "@/lib/api";

interface PropertyCardProps {
  record: PropertyRecordData;
}

function formatDate(raw: string): string {
  if (/^\d{8}$/.test(raw)) {
    const d = new Date(`${raw.slice(0, 4)}-${raw.slice(4, 6)}-${raw.slice(6, 8)}`);
    if (!isNaN(d.getTime())) return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  }
  const d = new Date(raw);
  return isNaN(d.getTime()) ? raw : d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function Stat({ label, value }: { label: string; value: string | number }) {
  if (!value || value === 0) return null;
  let display: string;
  if (typeof value === "number") {
    // Don't add commas to years (e.g. 1958 should NOT be "1,958")
    display = /year|built/i.test(label) ? value.toString() : value.toLocaleString();
  } else {
    // Format date strings (e.g. "20041001" → "Oct 1, 2004")
    display = /date/i.test(label) ? formatDate(value) : value;
  }
  return (
    <div className="rounded-lg bg-stone-50 p-2.5 transition-all hover:scale-[1.02] hover:shadow-sm">
      <div className="text-xs uppercase tracking-wider text-stone-500">{label}</div>
      <div className="mt-0.5 text-sm font-semibold text-stone-800">{display}</div>
    </div>
  );
}

export default function PropertyCard({ record }: PropertyCardProps) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-4">
        <Stat label="Folio" value={record.folio} />
        <Stat label="Lot Size" value={`${record.lot_size_sqft.toLocaleString()} sqft`} />
        <Stat label="Lot Dims" value={record.lot_dimensions} />
        <Stat label="Year Built" value={record.year_built} />
        <Stat label="Bedrooms" value={record.bedrooms} />
        <Stat label="Bathrooms" value={record.bathrooms} />
        <Stat label="Living Area" value={record.living_area_sqft ? `${record.living_area_sqft.toLocaleString()} sqft` : ""} />
        <Stat label="Building Area" value={record.building_area_sqft ? `${record.building_area_sqft.toLocaleString()} sqft` : ""} />
        <Stat label="Assessed" value={record.assessed_value ? `$${record.assessed_value.toLocaleString()}` : ""} />
        <Stat label="Market Value" value={record.market_value ? `$${record.market_value.toLocaleString()}` : ""} />
        <Stat label="Last Sale" value={record.last_sale_price ? `$${record.last_sale_price.toLocaleString()}` : ""} />
        <Stat label="Sale Date" value={record.last_sale_date} />
      </div>

      {record.owner && (
        <div className="text-xs text-stone-500">Owner: {record.owner}</div>
      )}
    </div>
  );
}
