"use client";

import { useState, useEffect } from "react";
import {
  APIProvider,
  Map,
  AdvancedMarker,
  InfoWindow,
  useMap,
} from "@vis.gl/react-google-maps";
import { openStreetMapStaticUrl, openStreetMapUrl } from "@/lib/mapAlternatives";

interface SatelliteMapProps {
  lat: number;
  lng: number;
  address: string;
  parcelGeometry?: number[][] | null;
}

const MAPS_KEY = process.env.NEXT_PUBLIC_GOOGLE_MAPS_KEY || "";

function StaticFallback({ lat, lng, address }: SatelliteMapProps) {
  const [imgError, setImgError] = useState(false);
  const [imgLoaded, setImgLoaded] = useState(false);
  const googleMapsUrl = `https://www.google.com/maps/@${lat},${lng},18z/data=!3m1!1e3`;
  const osmUrl = openStreetMapUrl(lat, lng, 18);

  if (MAPS_KEY && !imgError) {
    const staticUrl =
      `https://maps.googleapis.com/maps/api/staticmap` +
      `?center=${lat},${lng}` +
      `&zoom=18&size=600x200&scale=2&maptype=satellite` +
      `&markers=color:red|${lat},${lng}` +
      `&key=${MAPS_KEY}`;

    return (
      <a
        href={googleMapsUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="group relative block overflow-hidden rounded-lg"
      >
        {!imgLoaded && (
          <div className="h-[140px] w-full animate-pulse rounded-lg bg-[var(--bg-surface-raised)] sm:h-[180px]" />
        )}
        <img
          src={staticUrl}
          alt={`Satellite view of ${address}`}
          className={`h-[140px] w-full object-cover transition-transform duration-300 group-hover:scale-105 sm:h-[180px] ${imgLoaded ? "" : "absolute inset-0 opacity-0"}`}
          onLoad={() => setImgLoaded(true)}
          onError={() => setImgError(true)}
        />
      </a>
    );
  }

  if (!imgError) {
    const staticUrl = openStreetMapStaticUrl(lat, lng, 18);
    return (
      <a
        href={osmUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="group relative block overflow-hidden rounded-lg"
      >
        {!imgLoaded && (
          <div className="h-[140px] w-full animate-pulse rounded-lg bg-[var(--bg-surface-raised)] sm:h-[180px]" />
        )}
        <img
          src={staticUrl}
          alt={`Map view of ${address}`}
          className={`h-[140px] w-full object-cover transition-transform duration-300 group-hover:scale-105 sm:h-[180px] ${imgLoaded ? "" : "absolute inset-0 opacity-0"}`}
          onLoad={() => setImgLoaded(true)}
          onError={() => setImgError(true)}
        />
      </a>
    );
  }

  return (
    <a
      href={osmUrl}
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
        <div className="text-xs text-stone-500">
          View on OpenStreetMap
        </div>
    </a>
  );
}

export default function SatelliteMap({ lat, lng, address, parcelGeometry }: SatelliteMapProps) {
  void parcelGeometry;
  return <StaticFallback lat={lat} lng={lng} address={address} />;
}
