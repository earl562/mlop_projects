"use client";

import { useState, useEffect } from "react";

interface FloorPlanUnit {
  unit_id: string;
  area_sqft: number;
  width_ft: number;
  depth_ft: number;
  floor: number;
  label: string;
}

interface FloorPlanData {
  template: string;
  units: FloorPlanUnit[];
  total_units: number;
  stories: number;
  parking_spaces: number;
  notes: string[];
  svg: string;
}

interface FloorPlanViewerProps {
  buildableWidthFt: number;
  buildableDepthFt: number;
  maxHeightFt: number;
  maxUnits: number;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function FloorPlanViewer({
  buildableWidthFt,
  buildableDepthFt,
  maxHeightFt,
  maxUnits,
}: FloorPlanViewerProps) {
  const [data, setData] = useState<FloorPlanData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (buildableWidthFt <= 0 || buildableDepthFt <= 0) return;

    setLoading(true);
    setError(null);

    fetch(`${API_URL}/api/v1/geometry/floorplan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        buildable_width_ft: buildableWidthFt,
        buildable_depth_ft: buildableDepthFt,
        max_height_ft: maxHeightFt,
        max_units: maxUnits,
      }),
    })
      .then((res) => {
        if (!res.ok) throw new Error(`API error: ${res.status}`);
        return res.json();
      })
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, [buildableWidthFt, buildableDepthFt, maxHeightFt, maxUnits]);

  if (loading) {
    return (
      <div className="flex h-48 items-center justify-center rounded-lg border border-stone-200 bg-stone-50">
        <div className="text-sm text-stone-400">Generating floor plan...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-600">
        Floor plan unavailable: {error}
      </div>
    );
  }

  if (!data) return null;

  const templateLabel = data.template.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());

  return (
    <div className="space-y-3">
      {/* SVG Floor Plan */}
      <div className="-mx-1 overflow-x-auto sm:mx-0">
        <div
          className="min-w-[320px] rounded-lg border border-stone-200 bg-white p-2 sm:p-4"
          dangerouslySetInnerHTML={{ __html: data.svg }}
        />
      </div>

      {/* Summary bar */}
      <div className="flex flex-wrap gap-2 text-xs text-stone-600 sm:gap-4 sm:text-sm">
        <span className="font-medium text-stone-800">{templateLabel}</span>
        <span>{data.total_units} unit{data.total_units !== 1 ? "s" : ""}</span>
        <span>{data.stories} stor{data.stories !== 1 ? "ies" : "y"}</span>
        <span>{data.parking_spaces} parking</span>
      </div>

      {/* Unit breakdown */}
      {data.units.length > 1 && (
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {data.units.map((unit) => (
            <div key={unit.unit_id} className="rounded-md bg-stone-50 px-3 py-2 text-xs">
              <div className="font-medium text-stone-700">{unit.label}</div>
              <div className="text-stone-500">
                {unit.area_sqft.toFixed(0)} sqft · Floor {unit.floor}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Notes */}
      {data.notes.length > 0 && (
        <div className="space-y-1">
          {data.notes.map((note, i) => (
            <div key={i} className="text-xs text-stone-500">
              {note}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
