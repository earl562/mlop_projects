"use client";

import { useMemo } from "react";
import { generateFloorPlan, FloorPlanInput } from "@/lib/floorplan-generator";
import FloorPlanSVG from "./FloorPlanSVG";

interface FloorPlanViewerProps {
  buildableWidthFt: number;
  buildableDepthFt: number;
  maxHeightFt: number;
  maxStories: number;
  maxLotCoveragePct: number;
  far: number;
  maxUnits: number;
  minUnitSizeSqft: number;
  parkingPerUnit: number;
  lotSizeSqft: number;
  propertyType: string;
  zoningDistrict?: string;
}

export default function FloorPlanViewer(props: FloorPlanViewerProps) {
  const {
    buildableWidthFt, buildableDepthFt,
    maxHeightFt, maxStories, maxLotCoveragePct, far,
    maxUnits, minUnitSizeSqft, parkingPerUnit,
    lotSizeSqft, propertyType, zoningDistrict,
  } = props;

  const layout = useMemo(() => {
    if (buildableWidthFt <= 0 || buildableDepthFt <= 0) return null;
    return generateFloorPlan({
      buildableWidthFt,
      buildableDepthFt,
      maxHeightFt: maxHeightFt || 35,
      maxStories: maxStories || 2,
      maxLotCoveragePct: maxLotCoveragePct || 100,
      far: far || 0,
      maxUnits: maxUnits || 1,
      minUnitSizeSqft: minUnitSizeSqft || 400,
      parkingPerUnit: parkingPerUnit || 2,
      lotSizeSqft: lotSizeSqft || 0,
      propertyType: propertyType || "single_family",
    });
  }, [buildableWidthFt, buildableDepthFt, maxHeightFt, maxStories, maxLotCoveragePct, far, maxUnits, minUnitSizeSqft, parkingPerUnit, lotSizeSqft, propertyType]);

  if (!layout || !layout.rooms.length) {
    return (
      <div className="flex h-48 items-center justify-center rounded-lg border border-[var(--border)] bg-[var(--bg-surface-raised)]">
        <div className="text-sm text-stone-500">Buildable dimensions too small for floor plan</div>
      </div>
    );
  }

  return <FloorPlanSVG layout={layout} zoningDistrict={zoningDistrict} />;
}
