"use client";

import { useState, useEffect } from "react";
import {
  APIProvider,
  Map,
  AdvancedMarker,
  InfoWindow,
  useMap,
} from "@vis.gl/react-google-maps";

interface SatelliteMapProps {
  lat: number;
  lng: number;
  address: string;
  parcelGeometry?: number[][] | null;
}

const MAPS_KEY = process.env.NEXT_PUBLIC_GOOGLE_MAPS_KEY || "";

function ParcelOverlay({ geometry }: { geometry: number[][] }) {
  const map = useMap();

  useEffect(() => {
    if (!map || !geometry || geometry.length < 3) return;

    const paths = geometry.map(([lng, lat]) => ({ lat, lng }));

    const polygon = new google.maps.Polygon({
      paths,
      strokeColor: "#d97706",
      strokeOpacity: 0.9,
      strokeWeight: 2,
      fillColor: "#fbbf24",
      fillOpacity: 0.15,
      map,
    });

    return () => {
      polygon.setMap(null);
    };
  }, [map, geometry]);

  return null;
}

function InteractiveMap({ lat, lng, address, parcelGeometry }: SatelliteMapProps) {
  const [infoOpen, setInfoOpen] = useState(false);
  const position = { lat, lng };

  return (
    <div className="overflow-hidden rounded-lg border border-[var(--border)]">
      <Map
        defaultCenter={position}
        defaultZoom={18}
        mapTypeId="satellite"
        gestureHandling="cooperative"
        disableDefaultUI={false}
        mapTypeControl={false}
        streetViewControl={true}
        zoomControl={true}
        fullscreenControl={true}
        style={{ width: "100%", height: "220px" }}
        mapId="plotlot-satellite"
      >
        <AdvancedMarker position={position} onClick={() => setInfoOpen(true)} />
        {parcelGeometry && parcelGeometry.length >= 3 && (
          <ParcelOverlay geometry={parcelGeometry} />
        )}
        {infoOpen && (
          <InfoWindow position={position} onCloseClick={() => setInfoOpen(false)}>
            <div className="max-w-[200px] p-1">
              <p className="text-xs font-medium text-[var(--text-secondary)]">{address}</p>
              <p className="mt-0.5 text-xs text-stone-500">
                {lat.toFixed(6)}, {lng.toFixed(6)}
              </p>
            </div>
          </InfoWindow>
        )}
      </Map>
      {parcelGeometry && parcelGeometry.length >= 3 && (
        <div className="flex items-center gap-2 bg-[var(--bg-surface-raised)] px-3 py-1.5 text-xs text-stone-500">
          <div className="h-2.5 w-2.5 rounded-sm border border-amber-500 bg-amber-400/20" />
          Parcel boundary
        </div>
      )}
    </div>
  );
}

function StaticFallback({ lat, lng, address }: SatelliteMapProps) {
  const [imgError, setImgError] = useState(false);
  const [imgLoaded, setImgLoaded] = useState(false);
  const googleMapsUrl = `https://www.google.com/maps/@${lat},${lng},18z/data=!3m1!1e3`;

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

  return (
    <a
      href={googleMapsUrl}
      target="_blank"
      rel="noopener noreferrer"
      className="group flex min-h-[44px] items-center gap-3 rounded-lg border border-[var(--border)] bg-[var(--bg-surface-raised)] p-3 transition-all hover:border-amber-300 hover:bg-amber-50/50 dark:hover:bg-amber-950/30 sm:p-4"
    >
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-amber-100 text-amber-700 transition-colors group-hover:bg-amber-200 dark:bg-amber-950/50 dark:text-amber-400">
        <svg className="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
          <circle cx="12" cy="10" r="3" />
        </svg>
      </div>
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium text-[var(--text-secondary)] group-hover:text-amber-800">
          {address || "Open satellite view"}
        </div>
        <div className="text-xs text-stone-500">
          View on Google Maps
        </div>
      </div>
    </a>
  );
}

export default function SatelliteMap({ lat, lng, address, parcelGeometry }: SatelliteMapProps) {
  // Use interactive map when API key is available
  if (MAPS_KEY) {
    return (
      <APIProvider apiKey={MAPS_KEY}>
        <InteractiveMap lat={lat} lng={lng} address={address} parcelGeometry={parcelGeometry} />
      </APIProvider>
    );
  }

  // Fallback for no key
  return <StaticFallback lat={lat} lng={lng} address={address} />;
}
