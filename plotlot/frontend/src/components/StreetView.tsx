"use client";

import { useState } from "react";

interface StreetViewProps {
  lat: number;
  lng: number;
  address: string;
}

const MAPS_KEY = process.env.NEXT_PUBLIC_GOOGLE_MAPS_KEY || "";

export default function StreetView({ lat, lng, address }: StreetViewProps) {
  const [expanded, setExpanded] = useState(false);
  const [imgError, setImgError] = useState(false);
  const [imgLoaded, setImgLoaded] = useState(false);

  if (!MAPS_KEY) return null;

  const staticUrl =
    `https://maps.googleapis.com/maps/api/streetview` +
    `?size=600x300&location=${lat},${lng}` +
    `&fov=90&heading=0&pitch=5` +
    `&key=${MAPS_KEY}`;

  if (imgError) return null;

  return (
    <div className="space-y-2">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 text-left"
      >
        <svg
          className={`h-3.5 w-3.5 shrink-0 text-stone-500 transition-transform duration-200 ${expanded ? "rotate-90" : ""}`}
          viewBox="0 0 20 20"
          fill="currentColor"
        >
          <path fillRule="evenodd" d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z" clipRule="evenodd" />
        </svg>
        <h3 className="text-sm font-semibold uppercase tracking-wider text-stone-500">Street View</h3>
      </button>

      {expanded && (
        <div className="animate-fade-in overflow-hidden rounded-lg border border-stone-200 dark:border-stone-700">
          {!imgLoaded && (
            <div className="h-[200px] w-full animate-pulse bg-stone-200 dark:bg-stone-700 sm:h-[250px]" />
          )}
          <img
            src={staticUrl}
            alt={`Street view of ${address}`}
            className={`w-full object-cover ${imgLoaded ? "" : "absolute inset-0 opacity-0"}`}
            onLoad={() => setImgLoaded(true)}
            onError={() => setImgError(true)}
          />
          <div className="flex items-center justify-between bg-stone-50 dark:bg-stone-800 px-3 py-2">
            <span className="text-xs text-stone-500">Google Street View</span>
            <a
              href={`https://www.google.com/maps/@${lat},${lng},3a,75y,0h,90t/data=!3m1!1e1`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs font-medium text-amber-700 hover:text-amber-600"
            >
              Open full view
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
