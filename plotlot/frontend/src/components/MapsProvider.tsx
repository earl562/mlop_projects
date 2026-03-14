"use client";

import { APIProvider } from "@vis.gl/react-google-maps";

const MAPS_KEY = process.env.NEXT_PUBLIC_GOOGLE_MAPS_KEY || "";

export function MapsProvider({ children }: { children: React.ReactNode }) {
  if (!MAPS_KEY) return <>{children}</>;

  return (
    <APIProvider apiKey={MAPS_KEY}>
      {children}
    </APIProvider>
  );
}
