"use client";

import { useCallback, useRef, useState } from "react";

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

type RenderStatus = "idle" | "loading" | "ready" | "error";

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
  const [status, setStatus] = useState<RenderStatus>("idle");
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
      setError("Buildable area is too small for an AI visualization.");
      setStatus("error");
      return;
    }

    const cacheKey = [
      propType,
      stories,
      totalWidth,
      totalDepth,
      maxHeightFt,
      lotWidthFt,
      lotDepthFt,
      zoningDistrict,
      unitCount,
      setbackFrontFt,
      setbackSideFt,
      setbackRearFt,
      municipality,
    ].join("|");

    const cached = renderCache.current.get(cacheKey);
    if (cached) {
      setResult(cached);
      setError(null);
      setStatus("ready");
      return;
    }

    setStatus("loading");
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
      setStatus("ready");
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "The optional AI visualization could not be generated.",
      );
      setStatus("error");
    }
  }, [
    lotDepthFt,
    lotWidthFt,
    maxHeightFt,
    municipality,
    propType,
    setbackFrontFt,
    setbackRearFt,
    setbackSideFt,
    stories,
    totalDepth,
    totalWidth,
    unitCount,
    zoningDistrict,
  ]);

  const views = result?.views || [];
  const currentImage = views.find((view) => view.view === activeView) || views[0];

  const tabClass = (key: string) =>
    `rounded-full px-3.5 py-1.5 text-xs font-medium transition-all active:scale-[0.98] ${
      activeView === key
        ? "bg-[var(--text-primary)] text-[var(--bg-primary)]"
        : "border border-[var(--border)] text-[var(--text-muted)] hover:border-[var(--border-hover)] hover:text-[var(--text-secondary)]"
    }`;

  return (
    <div className="space-y-3">
      {status === "ready" && views.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {views.map((view) => (
            <button
              type="button"
              key={view.view}
              onClick={() => setActiveView(view.view)}
              className={tabClass(view.view)}
            >
              {VIEW_LABELS[view.view] || view.view}
            </button>
          ))}
        </div>
      ) : null}

      {status === "idle" ? (
        <div className="flex min-h-[260px] flex-col items-center justify-center gap-4 rounded-lg border border-[var(--border)] bg-[var(--bg-surface-raised)] px-6 text-center">
          <div className="space-y-2">
            <p className="text-sm font-medium text-[var(--text-primary)]">
              Optional AI visualization
            </p>
            <p className="max-w-lg text-sm text-[var(--text-muted)]">
              Generate conceptual architectural views from the modeled zoning envelope.
              This illustration is not part of the verified feasibility result and may
              require a configured image provider.
            </p>
          </div>
          <button
            type="button"
            onClick={fetchRender}
            className="rounded-full bg-[var(--text-primary)] px-5 py-2 text-sm font-medium text-[var(--bg-primary)] transition-opacity hover:opacity-85 active:scale-[0.98]"
          >
            Generate AI views
          </button>
        </div>
      ) : null}

      {status === "loading" ? (
        <div className="flex h-[400px] items-center justify-center rounded-lg border border-[var(--border)] bg-[var(--bg-surface-raised)]">
          <div className="flex flex-col items-center gap-3">
            <svg
              aria-hidden="true"
              className="h-6 w-6 animate-spin text-[var(--text-muted)]"
              viewBox="0 0 24 24"
              fill="none"
            >
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
              />
            </svg>
            <span className="text-sm text-[var(--text-muted)]">
              Generating conceptual architectural views...
            </span>
          </div>
        </div>
      ) : null}

      {status === "error" ? (
        <div className="flex min-h-[260px] flex-col items-center justify-center gap-3 rounded-lg border border-[var(--border)] bg-[var(--bg-surface-raised)] px-6 text-center">
          <svg
            aria-hidden="true"
            className="h-8 w-8 text-[var(--text-muted)]"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={1.5}
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909M3.75 21h16.5a1.5 1.5 0 001.5-1.5V5.25a1.5 1.5 0 00-1.5-1.5H3.75a1.5 1.5 0 00-1.5 1.5v14.25a1.5 1.5 0 001.5 1.5z"
            />
          </svg>
          <p className="text-sm text-[var(--text-muted)]">{error}</p>
          <p className="max-w-lg text-xs text-[var(--text-muted)]">
            The zoning, density, and financial analysis remains available; only the
            optional generated illustration failed.
          </p>
          <button
            type="button"
            onClick={fetchRender}
            className="rounded-full border border-[var(--border)] px-4 py-1.5 text-xs font-medium text-[var(--text-secondary)] transition-colors hover:border-[var(--border-hover)] hover:text-[var(--text-primary)] active:scale-[0.98]"
          >
            Retry
          </button>
        </div>
      ) : null}

      {status === "ready" && currentImage ? (
        <div className="overflow-hidden rounded-lg border border-[var(--border)]">
          <img
            src={`data:image/png;base64,${currentImage.image_base64}`}
            alt={`AI-rendered ${VIEW_LABELS[currentImage.view] || currentImage.view} view of ${propType.replace(/_/g, " ")} building`}
            className="w-full object-cover"
          />
        </div>
      ) : null}

      {status === "ready" && !currentImage ? (
        <div className="flex min-h-[220px] items-center justify-center rounded-lg border border-[var(--border)] bg-[var(--bg-surface-raised)] px-6 text-center text-sm text-[var(--text-muted)]">
          The image provider returned no views. The verified analysis is unchanged.
        </div>
      ) : null}

      <div className="flex items-center justify-between gap-4 text-xs text-[var(--text-muted)]">
        <span>
          {currentImage
            ? `${VIEW_LABELS[currentImage.view]}${
                result?.cached
                  ? " (cached)"
                  : ` — ${views.length} views in ${(
                      (result?.generation_time_ms || 0) / 1000
                    ).toFixed(1)}s`
              }`
            : status === "loading"
              ? "Generating AI views..."
              : "Concept visualization is optional"}
        </span>
        <span>
          {stories} stories, {totalWidth.toFixed(0)} × {totalDepth.toFixed(0)} ft
          footprint
        </span>
      </div>
    </div>
  );
}
