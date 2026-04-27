"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { renderBuilding, type BuildingRenderData } from "@/lib/api";

interface BuildingRenderViewerProps {
  lotWidthFt: number;
  lotDepthFt: number;
  setbackFrontFt: number;
  setbackSideFt: number;
  setbackRearFt: number;
  maxHeightFt: number;
  maxStories?: number;
  propertyType?: string;
  maxUnits?: number;
  zoningDistrict: string;
  municipality: string;
}

const VIEW_LABELS: Record<string, string> = {
  front: "Front",
  aerial: "Aerial",
  side: "Side",
};

export default function BuildingRenderViewer({
  lotWidthFt,
  lotDepthFt,
  setbackFrontFt,
  setbackSideFt,
  setbackRearFt,
  maxHeightFt,
  maxStories,
  propertyType,
  maxUnits,
  zoningDistrict,
  municipality,
}: BuildingRenderViewerProps) {
  const [result, setResult] = useState<BuildingRenderData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeView, setActiveView] = useState("front");
  const renderCache = useRef<Map<string, BuildingRenderData>>(new Map());

  const totalWidth = Math.max(0, lotWidthFt - 2 * setbackSideFt);
  const totalDepth = Math.max(0, lotDepthFt - setbackFrontFt - setbackRearFt);
  const stories = maxStories || Math.min(Math.floor(maxHeightFt / 10), 4) || 2;
  const unitCount = maxUnits || 1;
  const propType = propertyType || "single_family";

  const fetchRender = useCallback(async () => {
    if (totalWidth <= 0 || totalDepth <= 0) {
      setError("Buildable area too small for AI rendering");
      setLoading(false);
      return;
    }

    const cacheKey = [propType, stories, totalWidth, totalDepth, maxHeightFt,
      lotWidthFt, lotDepthFt, zoningDistrict, unitCount,
      setbackFrontFt, setbackSideFt, setbackRearFt, municipality].join("|");

    const cached = renderCache.current.get(cacheKey);
    if (cached) {
      setResult(cached);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const data = await renderBuilding({
        property_type: propType,
        stories,
        total_width_ft: totalWidth,
        total_depth_ft: totalDepth,
        max_height_ft: maxHeightFt,
        lot_width_ft: lotWidthFt,
        lot_depth_ft: lotDepthFt,
        zoning_district: zoningDistrict,
        unit_count: unitCount,
        setback_front_ft: setbackFrontFt,
        setback_side_ft: setbackSideFt,
        setback_rear_ft: setbackRearFt,
        municipality,
      });
      renderCache.current.set(cacheKey, data);
      setResult(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate AI rendering");
    } finally {
      setLoading(false);
    }
  }, [
    totalWidth, totalDepth, maxHeightFt, lotWidthFt, lotDepthFt,
    zoningDistrict, unitCount, setbackFrontFt, setbackSideFt, setbackRearFt,
    municipality, propType, stories,
  ]);

  useEffect(() => {
    fetchRender();
  }, [fetchRender]);

  const views = result?.views || [];
  const currentImage = views.find((v) => v.view === activeView) || views[0];

  const tabClass = (key: string) =>
    `rounded-full px-3.5 py-1.5 text-xs font-medium transition-all active:scale-[0.98] ${
      activeView === key
        ? "bg-[var(--text-primary)] text-[var(--bg-primary)]"
        : "border border-[var(--border)] text-[var(--text-muted)] hover:border-[var(--border-hover)] hover:text-[var(--text-secondary)]"
    }`;

  return (
    <div className="space-y-3">
      {/* View tabs */}
      <div className="flex flex-wrap gap-2">
        {views.length > 0
          ? views.map((v) => (
              <button key={v.view} onClick={() => setActiveView(v.view)} className={tabClass(v.view)}>
                {VIEW_LABELS[v.view] || v.view}
              </button>
            ))
          : ["front", "aerial", "side"].map((v) => (
              <button
                key={v}
                disabled={loading}
                className="inline-flex items-center gap-1.5 rounded-full border border-[var(--border)] px-3.5 py-1.5 text-xs font-medium text-[var(--text-muted)] opacity-60"
              >
                {loading && (
                  <svg className="h-3 w-3 animate-spin" viewBox="0 0 24 24" fill="none">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                  </svg>
                )}
                {VIEW_LABELS[v]}
              </button>
            ))
        }
      </div>

      {/* Content */}
      {loading ? (
        <div className="flex h-[400px] items-center justify-center rounded-lg border border-[var(--border)] bg-[var(--bg-surface-raised)]">
          <div className="flex flex-col items-center gap-3">
            <svg className="h-6 w-6 animate-spin text-[var(--text-muted)]" viewBox="0 0 24 24" fill="none">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
            <span className="text-sm text-[var(--text-muted)]">Generating AI architectural views...</span>
          </div>
        </div>
      ) : error ? (
        <div className="flex h-[300px] flex-col items-center justify-center gap-3 rounded-lg border border-[var(--border)] bg-[var(--bg-surface-raised)]">
          <svg className="h-8 w-8 text-[var(--text-muted)]" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909M3.75 21h16.5a1.5 1.5 0 001.5-1.5V5.25a1.5 1.5 0 00-1.5-1.5H3.75a1.5 1.5 0 00-1.5 1.5v14.25a1.5 1.5 0 001.5 1.5z" />
          </svg>
          <p className="text-sm text-[var(--text-muted)]">{error}</p>
          <button
            onClick={fetchRender}
            className="rounded-full border border-[var(--border)] px-4 py-1.5 text-xs font-medium text-[var(--text-secondary)] transition-colors hover:border-[var(--border-hover)] hover:text-[var(--text-primary)] active:scale-[0.98]"
          >
            Retry
          </button>
        </div>
      ) : currentImage ? (
        <div className="overflow-hidden rounded-lg border border-[var(--border)]">
          <img
            src={`data:image/png;base64,${currentImage.image_base64}`}
            alt={`AI-rendered ${VIEW_LABELS[currentImage.view] || currentImage.view} view of ${propType.replace(/_/g, " ")} building`}
            className="w-full object-cover"
          />
        </div>
      ) : null}

      {/* Caption */}
      <div className="flex items-center justify-between text-xs text-[var(--text-muted)]">
        <span>
          {currentImage
            ? `${VIEW_LABELS[currentImage.view]}${result?.cached ? " (cached)" : ` — ${views.length} views in ${((result?.generation_time_ms || 0) / 1000).toFixed(1)}s`}`
            : loading
              ? "Loading AI views..."
              : ""}
        </span>
        <span>{stories} stories, {totalWidth.toFixed(0)} x {totalDepth.toFixed(0)} ft footprint</span>
      </div>
    </div>
  );
}
