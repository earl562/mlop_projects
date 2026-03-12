"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type LayerKey = "zoning" | "flood" | "boundaries" | "dimensions";

interface ArcGISParcelMapProps {
  lat: number;
  lng: number;
  county: string;
  parcelGeometry?: number[][] | null;
  lotDimensions?: string;
  lotSizeSqft?: number;
  onFloodZone?: (zone: string, sfha: boolean) => void;
}

// County ArcGIS MapServer URLs — public, no auth required
const COUNTY_MAP_SERVERS: Record<string, { url: string; layers?: number[] }> = {
  "Miami-Dade": {
    url: "https://gisweb.miamidade.gov/arcgis/rest/services/LandManagement/MD_Zoning/MapServer",
  },
  "Broward": {
    url: "https://gisweb-adapters.bcpa.net/arcgis/rest/services/BCPA_EXTERNAL_JAN26/MapServer",
    layers: [16],
  },
  "Palm Beach": {
    url: "https://maps.co.palm-beach.fl.us/arcgis/rest/services/OpenData/Planning_Open_Data/MapServer",
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
];

function LayerToggleChips({
  activeLayers,
  onToggle,
}: {
  activeLayers: Set<LayerKey>;
  onToggle: (key: LayerKey) => void;
}) {
  return (
    <div className="flex gap-1.5 border-b border-[var(--border)] px-3 py-2">
      {LAYER_CHIPS.map((chip) => {
        const active = activeLayers.has(chip.key);
        return (
          <button
            key={chip.key}
            onClick={() => onToggle(chip.key)}
            className={`rounded-full px-2.5 py-1 text-[11px] font-medium transition-colors ${
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
  onFloodZone,
}: ArcGISParcelMapProps) {
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);

  // Layer refs
  const zoningLayerRef = useRef<L.Layer | null>(null);
  const polygonLayerRef = useRef<L.Layer | null>(null);
  const dimensionLayerRef = useRef<L.LayerGroup | null>(null);
  const floodLayerRef = useRef<L.Layer | null>(null);

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

    // Base tile layer
    L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
      maxZoom: 22,
    }).addTo(map);

    // --- Zoning ArcGIS layer (created but NOT added — default OFF) ---
    const countyConfig = COUNTY_MAP_SERVERS[county];
    if (countyConfig) {
      import("esri-leaflet")
        .then((esri) => {
          const arcgisLayer = esri.dynamicMapLayer({
            url: countyConfig.url,
            opacity: 0.6,
            layers: countyConfig.layers,
            f: "image",
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
    };
  }, [lat, lng, county, parcelGeometry]);

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
              url: "https://hazards.fema.gov/gis/nfhl/rest/services/public/NFHL/MapServer",
              opacity: 0.5,
              layers: [28],
            });
            floodLayerRef.current = floodLayer;
            if (mapInstanceRef.current && activeLayersRef.current.has("flood")) {
              floodLayer.addTo(mapInstanceRef.current);
            }

            // FEMA identify query for flood zone designation
            const identifyUrl =
              `https://hazards.fema.gov/gis/nfhl/rest/services/public/NFHL/MapServer/identify` +
              `?geometry=${lng},${lat}` +
              `&geometryType=esriGeometryPoint` +
              `&layers=all:28` +
              `&tolerance=1` +
              `&returnGeometry=false` +
              `&f=json` +
              `&mapExtent=${lng - 0.01},${lat - 0.01},${lng + 0.01},${lat + 0.01}` +
              `&imageDisplay=400,400,96`;

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

  return (
    <div className="relative flex h-full w-full flex-col">
      {/* Toggle chips — above the map, below tab bar */}
      <LayerToggleChips activeLayers={activeLayers} onToggle={handleToggle} />

      {/* Map */}
      <div ref={mapRef} className="flex-1" style={{ minHeight: "220px" }} />

      {/* Legend */}
      <div className="absolute bottom-0 left-0 right-0 z-[1000] flex items-center gap-2 bg-[var(--bg-surface)]/90 px-3 py-1.5 text-xs text-[var(--text-muted)] backdrop-blur-sm">
        <div className="h-2.5 w-2.5 rounded-sm border border-emerald-600 bg-emerald-500/20" />
        <span>Parcel boundary</span>
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
