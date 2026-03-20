"use client";

import { APIProvider } from "@vis.gl/react-google-maps";

const MAPS_KEY = process.env.NEXT_PUBLIC_GOOGLE_MAPS_KEY || "";

// Patch console.error at module load to suppress Google Maps SDK errors that
// fire synchronously before React's onError handler can intercept them.
// ApiNotActivatedMapError = Maps JavaScript API (tiles) not enabled.
// Autocomplete still works via the Places API, so this is cosmetic-only.
if (typeof window !== "undefined" && MAPS_KEY) {
  const _originalError = console.error.bind(console);
  console.error = (...args: unknown[]) => {
    const msg = typeof args[0] === "string" ? args[0] : "";
    if (msg.includes("ApiNotActivated") || msg.includes("InvalidKey")) return;
    _originalError(...args);
  };
}

function handleMapsError(e: unknown) {
  if (e instanceof Error && e.message?.includes("ApiNotActivated")) return;
  console.error("[Maps]", e);
}

export function MapsProvider({ children }: { children: React.ReactNode }) {
  if (!MAPS_KEY) return <>{children}</>;

  return (
    <APIProvider apiKey={MAPS_KEY} onError={handleMapsError}>
      {children}
    </APIProvider>
  );
}
