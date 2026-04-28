"use client";

interface SatelliteMapProps {
  lat: number;
  lng: number;
  address: string;
  parcelGeometry?: number[][] | null;
}

function StaticFallback({ lat, lng, address }: SatelliteMapProps) {
  const openStreetMapUrl = `https://www.openstreetmap.org/?mlat=${lat}&mlon=${lng}#map=18/${lat}/${lng}`;

  return (
    <a
      href={openStreetMapUrl}
      target="_blank"
      rel="noopener noreferrer"
      className="group flex min-h-[44px] items-center gap-3 rounded-lg border border-[var(--border)] bg-[var(--bg-surface-raised)] p-3 transition-all hover:border-amber-300 hover:bg-amber-50/50 dark:hover:bg-amber-950/30 sm:p-4"
      >
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-amber-100 text-amber-700 transition-colors group-hover:bg-amber-200 dark:bg-amber-950/50 dark:text-amber-400">
          <svg aria-hidden="true" className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
            <circle cx="12" cy="10" r="3" />
          </svg>
        </div>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium text-[var(--text-secondary)] group-hover:text-amber-800">
            {address || "Open satellite view"}
          </div>
          <div className="text-xs text-stone-500">
            Open in OpenStreetMap
          </div>
        </div>
    </a>
  );
}

export default function SatelliteMap({ lat, lng, address, parcelGeometry }: SatelliteMapProps) {
  void parcelGeometry;
  return <StaticFallback lat={lat} lng={lng} address={address} />;
}
