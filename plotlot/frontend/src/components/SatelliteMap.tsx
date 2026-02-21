"use client";

import { useState } from "react";

interface SatelliteMapProps {
  lat: number;
  lng: number;
  address: string;
}

const MAPS_KEY = process.env.NEXT_PUBLIC_GOOGLE_MAPS_KEY || "";

export default function SatelliteMap({ lat, lng, address }: SatelliteMapProps) {
  const [imgError, setImgError] = useState(false);

  const googleMapsUrl = `https://www.google.com/maps/@${lat},${lng},18z/data=!3m1!1e3`;

  // If Google Maps Static API key is configured, show satellite image
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
        className="group block overflow-hidden rounded-lg"
      >
        <img
          src={staticUrl}
          alt={`Satellite view of ${address}`}
          className="h-[180px] w-full object-cover transition-transform duration-300 group-hover:scale-105"
          onError={() => setImgError(true)}
        />
      </a>
    );
  }

  // Fallback: styled link that opens Google Maps satellite view
  return (
    <a
      href={googleMapsUrl}
      target="_blank"
      rel="noopener noreferrer"
      className="group flex items-center gap-3 rounded-lg border border-stone-200 bg-stone-50 p-4 transition-all hover:border-amber-300 hover:bg-amber-50/50"
    >
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-amber-100 text-amber-700 transition-colors group-hover:bg-amber-200">
        <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
          <circle cx="12" cy="10" r="3" />
        </svg>
      </div>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-medium text-stone-700 group-hover:text-amber-800">
          View on Google Maps
        </div>
        <div className="truncate text-xs text-stone-500">
          {lat.toFixed(6)}, {lng.toFixed(6)} &middot; Satellite view
        </div>
      </div>
      <svg className="h-4 w-4 shrink-0 text-stone-400 transition-transform group-hover:translate-x-0.5 group-hover:text-amber-600" viewBox="0 0 20 20" fill="currentColor">
        <path fillRule="evenodd" d="M5.22 14.78a.75.75 0 010-1.06l7.22-7.22H8.75a.75.75 0 010-1.5h5.5a.75.75 0 01.75.75v5.5a.75.75 0 01-1.5 0V7.06l-7.22 7.22a.75.75 0 01-1.06 0z" clipRule="evenodd" />
      </svg>
    </a>
  );
}
