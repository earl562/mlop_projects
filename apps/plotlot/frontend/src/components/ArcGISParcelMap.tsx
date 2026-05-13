"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type LayerKey = "zoning" | "flood" | "boundaries" | "dimensions" | "water" | "topography" | "wetlands";

interface ArcGISParcelMapProps {
  lat: number;
  lng: number;
  county: string;
  parcelGeometry?: number[][] | null;
  lotDimensions?: string;
  lotSizeSqft?: number;
  zoningLayerUrl?: string;
  onFloodZone?: (zone: string, sfha: boolean) => void;
}

// Zoning layer uses the URL provided by the backend property record (zoningLayerUrl prop).
// No hardcoded county fallbacks — county MapServers show broad district data that
// doesn't accurately represent a specific parcel's zoning classification.

// GIS overlay service URLs — public, CORS-enabled, no auth required
const TOPOGRAPHY_URL = "https://carto.nationalmap.gov/arcgis/rest/services/contours/MapServer";
const WETLANDS_URL = "https://fwspublicservices.wim.usgs.gov/wetlandsmapservice/rest/services/Wetlands/MapServer";

const COUNTY_WATER_SERVERS: Record<string, { url: string; layers?: number[] }> = {
  "Miami-Dade": {
    url: "https://gisweb.miamidade.gov/arcgis/rest/services/Wasd/WaterAndSewerServiceAreasExtended_1_v1/MapServer",
    layers: [0, 1],
  },
};

// ---------------------------------------------------------------------------
// Haversine distance (returns feet)
// ---------------------------------------------------------------------------

function haversineFt(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 20902231; // Earth radius in feet
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

// ---------------------------------------------------------------------------
// Toggle Chips
// ---------------------------------------------------------------------------

const LAYER_CHIPS: { key: LayerKey; label: string }[] = [
  { key: "zoning", label: "Zoning" },
  { key: "flood", label: "Flood Zone" },
  { key: "boundaries", label: "Boundaries" },
  { key: "dimensions", label: "Dimensions" },
  { key: "water", label: "Water & Sewer" },
  { key: "topography", label: "Topography" },
  { key: "wetlands", label: "Wetlands" },
];

function LayerToggleChips({
  activeLayers,
  onToggle,
}: {
  activeLayers: Set<LayerKey>;
  onToggle: (key: LayerKey) => void;
}) {
  return (
    <div className="flex gap-1.5 overflow-x-auto border-b border-[var(--border)] px-3 py-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
      {LAYER_CHIPS.map((chip) => {
        const active = activeLayers.has(chip.key);
        return (
          <button
            key={chip.key}
            onClick={() => onToggle(chip.key)}
            className={`shrink-0 rounded-full px-2.5 py-1 text-[11px] font-medium transition-colors ${
              active
                ? "bg-emerald-600 text-white"
                : "border border-[var(--border)] text-[var(--text-muted)] hover:border-[var(--border-hover)] hover:text-[var(--text-secondary)]"
            }`}
          >
            {active && <span className="mr-1">&#9632;</span>}
            {chip.label}
          </button>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ArcGISParcelMap
// ---------------------------------------------------------------------------

export default function ArcGISParcelMap({
  lat,
  lng,
  county,
  parcelGeometry,
  lotDimensions,
  zoningLayerUrl,
  onFloodZone,
}: ArcGISParcelMapProps) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);

  // Layer refs
  const zoningLayerRef = useRef<L.Layer | null>(null);
  const polygonLayerRef = useRef<L.Layer | null>(null);
  const dimensionLayerRef = useRef<L.LayerGroup | null>(null);
  const floodLayerRef = useRef<L.Layer | null>(null);
  const waterLayerRef = useRef<L.Layer | null>(null);
  const topographyLayerRef = useRef<L.Layer | null>(null);
  const wetlandsLayerRef = useRef<L.Layer | null>(null);

  // Stable ref for callback to avoid effect dependency issues
  const onFloodZoneRef = useRef(onFloodZone);
  onFloodZoneRef.current = onFloodZone;

  // Ref for current activeLayers so async callbacks can read latest value
  const activeLayersRef = useRef<Set<LayerKey>>(new Set(["boundaries", "dimensions"]));

  // State
  const [activeLayers, setActiveLayers] = useState<Set<LayerKey>>(
    new Set(["boundaries", "dimensions"]),
  );
  const [floodZone, setFloodZone] = useState<{ zone: string; sfha: boolean } | null>(null);

  // Keep ref in sync
  activeLayersRef.current = activeLayers;

  // Toggle handler
  const handleToggle = useCallback((key: LayerKey) => {
    setActiveLayers((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }, []);

  // --- Map initialization ---
  useEffect(() => {
    if (!mapRef.current || mapInstanceRef.current) return;

    const map = L.map(mapRef.current, {
      center: [lat, lng],
      zoom: 18,
      zoomControl: true,
      attributionControl: false,
    });

    mapInstanceRef.current = map;

    // Base tile layer — ESRI World Imagery (satellite)
    L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
      maxZoom: 19,
    }).addTo(map);

    // --- Zoning ArcGIS layer (created but NOT added — default OFF) ---
    // Only renders if the backend provides a specific zoning layer URL for this parcel.
    if (zoningLayerUrl) {
      import("esri-leaflet")
        .then((esri) => {
          const arcgisLayer = esri.dynamicMapLayer({
            url: zoningLayerUrl,
            opacity: 0.6,
            proxy: "/api/gis-proxy",
          });
          zoningLayerRef.current = arcgisLayer;
          // Add if user already toggled zoning ON before import completed
          if (activeLayersRef.current.has("zoning") && mapInstanceRef.current) {
            arcgisLayer.addTo(mapInstanceRef.current);
          }
        })
        .catch((err) => {
          console.warn("Failed to load ArcGIS layer:", err);
        });
    }

    // --- Parcel polygon + dimension labels ---
    if (parcelGeometry && parcelGeometry.length >= 3) {
      const latlngs: L.LatLngExpression[] = parcelGeometry.map(
        ([lngCoord, latCoord]) => [latCoord, lngCoord],
      );

      const polygon = L.polygon(latlngs, {
        color: "#059669",
        weight: 3,
        opacity: 0.9,
        fillColor: "#10b981",
        fillOpacity: 0.2,
      });
      polygonLayerRef.current = polygon;
      polygon.addTo(map); // Boundaries default ON

      // Fit map to parcel bounds
      map.fitBounds(polygon.getBounds(), { padding: [40, 40] });

      // --- Dimension labels on edges ---
      const dimGroup = L.layerGroup();
      for (let i = 0; i < parcelGeometry.length; i++) {
        const [lng1, lat1] = parcelGeometry[i];
        const [lng2, lat2] = parcelGeometry[(i + 1) % parcelGeometry.length];
        const dist = haversineFt(lat1, lng1, lat2, lng2);

        if (dist < 10) continue; // Skip tiny segments

        const midLat = (lat1 + lat2) / 2;
        const midLng = (lng1 + lng2) / 2;

        // Edge angle for label rotation
        let angle = (Math.atan2(-(lat2 - lat1), lng2 - lng1) * 180) / Math.PI;
        if (angle > 90) angle -= 180;
        if (angle < -90) angle += 180;

        const label = L.marker([midLat, midLng], {
          icon: L.divIcon({
            className: "dimension-label",
            html: `<span style="
              background: rgba(255,255,255,0.95);
              border: 1px solid #059669;
              border-radius: 3px;
              padding: 1px 4px;
              font-size: 10px;
              font-weight: 600;
              color: #059669;
              white-space: nowrap;
              transform: rotate(${angle}deg);
              display: inline-block;
              pointer-events: none;
            ">${Math.round(dist)}ft</span>`,
            iconSize: [0, 0],
            iconAnchor: [0, 0],
          }),
          interactive: false,
        });
        dimGroup.addLayer(label);
      }
      dimensionLayerRef.current = dimGroup;
      dimGroup.addTo(map); // Dimensions default ON
    }

    // Center marker
    L.circleMarker([lat, lng], {
      radius: 6,
      color: "#059669",
      fillColor: "#10b981",
      fillOpacity: 1,
      weight: 2,
    }).addTo(map);

    return () => {
      map.remove();
      mapInstanceRef.current = null;
      zoningLayerRef.current = null;
      polygonLayerRef.current = null;
      dimensionLayerRef.current = null;
      floodLayerRef.current = null;
      waterLayerRef.current = null;
      topographyLayerRef.current = null;
      wetlandsLayerRef.current = null;
    };
  }, [lat, lng, parcelGeometry, zoningLayerUrl]);

  // --- Layer toggle effect (boundaries, dimensions, zoning) ---
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    // Boundaries
    if (polygonLayerRef.current) {
      if (activeLayers.has("boundaries") && !map.hasLayer(polygonLayerRef.current)) {
        polygonLayerRef.current.addTo(map);
      } else if (!activeLayers.has("boundaries") && map.hasLayer(polygonLayerRef.current)) {
        map.removeLayer(polygonLayerRef.current);
      }
    }

    // Dimensions
    if (dimensionLayerRef.current) {
      if (activeLayers.has("dimensions") && !map.hasLayer(dimensionLayerRef.current)) {
        dimensionLayerRef.current.addTo(map);
      } else if (!activeLayers.has("dimensions") && map.hasLayer(dimensionLayerRef.current)) {
        map.removeLayer(dimensionLayerRef.current);
      }
    }

    // Zoning
    if (zoningLayerRef.current) {
      if (activeLayers.has("zoning") && !map.hasLayer(zoningLayerRef.current)) {
        zoningLayerRef.current.addTo(map);
      } else if (!activeLayers.has("zoning") && map.hasLayer(zoningLayerRef.current)) {
        map.removeLayer(zoningLayerRef.current);
      }
    }
  }, [activeLayers]);

  // --- Flood toggle effect (async — separate from sync toggles) ---
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    if (activeLayers.has("flood")) {
      if (!floodLayerRef.current) {
        import("esri-leaflet")
          .then((esri) => {
            const floodLayer = esri.dynamicMapLayer({
              url: "https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer",
              opacity: 0.5,
              layers: [28],
                            proxy: "/api/gis-proxy",
            });
            floodLayerRef.current = floodLayer;
            if (mapInstanceRef.current && activeLayersRef.current.has("flood")) {
              floodLayer.addTo(mapInstanceRef.current);
            }

            // FEMA identify query for flood zone designation — routed through proxy (CORS)
            const identifyBase =
              `https://hazards.fema.gov/arcgis/rest/services/public/NFHL/MapServer/identify` +
              `?geometry=${lng},${lat}` +
              `&geometryType=esriGeometryPoint` +
              `&layers=all:28` +
              `&tolerance=1` +
              `&returnGeometry=false` +
              `&f=json` +
              `&mapExtent=${lng - 0.01},${lat - 0.01},${lng + 0.01},${lat + 0.01}` +
              `&imageDisplay=400,400,96`;
            const identifyUrl = `/api/gis-proxy?${identifyBase}`;

            fetch(identifyUrl)
              .then((r) => r.json())
              .then((data) => {
                if (data.results && data.results.length > 0) {
                  const attrs = data.results[0].attributes;
                  const zone = attrs.FLD_ZONE || "Unknown";
                  const sfha = attrs.SFHA_TF === "T" || attrs.SFHA_TF === true;
                  setFloodZone({ zone, sfha });
                  onFloodZoneRef.current?.(zone, sfha);
                }
              })
              .catch((err) => console.warn("FEMA identify failed:", err));
          })
          .catch((err) => {
            console.warn("Failed to load FEMA layer:", err);
          });
      }
    } else {
      // Flood OFF — remove layer and clear state
      if (floodLayerRef.current && map.hasLayer(floodLayerRef.current)) {
        map.removeLayer(floodLayerRef.current);
      }
      floodLayerRef.current = null;
      setFloodZone(null);
    }
  }, [activeLayers, lat, lng]);

  // --- Water/Sewer toggle effect (county-gated) ---
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    if (activeLayers.has("water")) {
      const waterConfig = COUNTY_WATER_SERVERS[county];
      if (!waterConfig) return; // No service for this county — silent no-op

      if (!waterLayerRef.current) {
        import("esri-leaflet")
          .then((esri) => {
            const waterLayer = esri.dynamicMapLayer({
              url: waterConfig.url,
              opacity: 0.6,
              layers: waterConfig.layers,
                            proxy: "/api/gis-proxy",
            });
            waterLayerRef.current = waterLayer;
            if (mapInstanceRef.current && activeLayersRef.current.has("water")) {
              waterLayer.addTo(mapInstanceRef.current);
            }
          })
          .catch((err) => console.warn("Failed to load water/sewer layer:", err));
      }
    } else {
      if (waterLayerRef.current && map.hasLayer(waterLayerRef.current)) {
        map.removeLayer(waterLayerRef.current);
      }
      waterLayerRef.current = null;
    }
  }, [activeLayers, county]);

  // --- Topography toggle effect ---
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    if (activeLayers.has("topography")) {
      if (!topographyLayerRef.current) {
        import("esri-leaflet")
          .then((esri) => {
            const topoLayer = esri.dynamicMapLayer({
              url: TOPOGRAPHY_URL,
              opacity: 0.7,
                            proxy: "/api/gis-proxy",
            });
            topographyLayerRef.current = topoLayer;
            if (mapInstanceRef.current && activeLayersRef.current.has("topography")) {
              topoLayer.addTo(mapInstanceRef.current);
            }
          })
          .catch((err) => console.warn("Failed to load topography layer:", err));
      }
    } else {
      if (topographyLayerRef.current && map.hasLayer(topographyLayerRef.current)) {
        map.removeLayer(topographyLayerRef.current);
      }
      topographyLayerRef.current = null;
    }
  }, [activeLayers]);

  // --- Wetlands toggle effect ---
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    if (activeLayers.has("wetlands")) {
      if (!wetlandsLayerRef.current) {
        import("esri-leaflet")
          .then((esri) => {
            const wetlandsLayer = esri.dynamicMapLayer({
              url: WETLANDS_URL,
              opacity: 0.5,
                            proxy: "/api/gis-proxy",
            });
            wetlandsLayerRef.current = wetlandsLayer;
            if (mapInstanceRef.current && activeLayersRef.current.has("wetlands")) {
              wetlandsLayer.addTo(mapInstanceRef.current);
            }
          })
          .catch((err) => console.warn("Failed to load wetlands layer:", err));
      }
    } else {
      if (wetlandsLayerRef.current && map.hasLayer(wetlandsLayerRef.current)) {
        map.removeLayer(wetlandsLayerRef.current);
      }
      wetlandsLayerRef.current = null;
    }
  }, [activeLayers]);

  return (
    <div className="relative flex h-full w-full flex-col">
      {/* Toggle chips — above the map, below tab bar */}
      <LayerToggleChips activeLayers={activeLayers} onToggle={handleToggle} />

      {/* Map */}
      <div ref={mapRef} className="flex-1" style={{ minHeight: "220px" }} />

      {/* Missing geometry notice */}
      {(!parcelGeometry || parcelGeometry.length < 3) && (
        <div className="absolute left-3 top-14 z-[1000] max-w-[200px] rounded-lg border border-amber-300 bg-amber-50/95 px-2.5 py-2 text-[11px] text-amber-700 shadow-sm backdrop-blur-sm dark:border-amber-800 dark:bg-amber-950/90 dark:text-amber-400">
          <div className="flex items-start gap-1.5">
            <svg className="mt-0.5 h-3 w-3 shrink-0" viewBox="0 0 20 20" fill="currentColor">
              <path fillRule="evenodd" d="M8.485 2.495c.673-1.167 2.357-1.167 3.03 0l6.28 10.875c.673 1.167-.168 2.625-1.516 2.625H3.72c-1.347 0-2.189-1.458-1.515-2.625L8.485 2.495zM10 6a.75.75 0 01.75.75v3.5a.75.75 0 01-1.5 0v-3.5A.75.75 0 0110 6zm0 9a1 1 0 100-2 1 1 0 000 2z" clipRule="evenodd" />
            </svg>
            <span>Parcel boundary unavailable — showing approximate location</span>
          </div>
        </div>
      )}

      {/* Legend */}
      <div className="absolute bottom-0 left-0 right-0 z-[1000] flex items-center gap-2 bg-[var(--bg-surface)]/90 px-3 py-1.5 text-xs text-[var(--text-muted)] backdrop-blur-sm">
        <div className="h-2.5 w-2.5 rounded-sm border border-emerald-600 bg-emerald-500/20" />
        <span>{parcelGeometry && parcelGeometry.length >= 3 ? "Parcel boundary" : "Approx. location"}</span>
        {lotDimensions && (
          <>
            <span className="text-[var(--text-secondary)]">&middot;</span>
            <span className="font-medium text-[var(--text-secondary)]">{lotDimensions}</span>
          </>
        )}
        {floodZone && (
          <>
            <span className="text-[var(--text-secondary)]">&middot;</span>
            <div className="h-2.5 w-2.5 rounded-sm border border-blue-600 bg-blue-500/30" />
            <span>
              Flood: {floodZone.zone} ({floodZone.sfha ? "SFHA" : "Minimal"})
            </span>
          </>
        )}
        <span className="ml-auto text-[10px] font-medium text-[var(--text-secondary)]">
          {county} County GIS
        </span>
      </div>
    </div>
  );
}
