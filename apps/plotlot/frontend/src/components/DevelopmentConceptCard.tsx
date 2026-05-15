"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { springGentle, fadeUp } from "@/lib/motion";

interface DevelopmentConceptCardProps {
  address: string;
  municipality: string;
  zoningDistrict: string;
  propertyType: string;
  maxUnits: number;
  lotSqft: number;
}

export default function DevelopmentConceptCard({
  address,
  municipality,
  zoningDistrict,
  propertyType,
  maxUnits,
  lotSqft,
}: DevelopmentConceptCardProps) {
  const [imageBase64, setImageBase64] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const typeLabel = propertyType
    .replace("commercial_mf", "multifamily complex")
    .replace("_", " ");

  const handleGenerate = async () => {
    setIsLoading(true);
    setError(null);
    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const resp = await fetch(`${API_URL}/api/v1/render/concept`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          address,
          municipality,
          zoning_district: zoningDistrict,
          property_type: propertyType,
          max_units: maxUnits,
          lot_sqft: lotSqft,
        }),
      });
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.detail || `Render failed: ${resp.status}`);
      }
      const data = await resp.json();
      setImageBase64(data.image_base64);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate concept render");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div
      className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)]"
      style={{ boxShadow: "var(--shadow-card)" }}
    >
      <AnimatePresence mode="wait">
        {/* CTA state */}
        {!imageBase64 && !isLoading && !error && (
          <motion.button
            key="cta"
            {...fadeUp}
            transition={springGentle}
            onClick={handleGenerate}
            className="group flex w-full items-center justify-between gap-3 p-4 text-left transition-colors hover:bg-[var(--bg-surface-raised)] sm:p-5"
          >
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-amber-100 dark:bg-amber-950/50">
                <svg
                  className="h-5 w-5 text-amber-600"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={1.5}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M2.25 21h19.5m-18-18v18m10.5-18v18m6-13.5V21M6.75 6.75h.75m-.75 3h.75m-.75 3h.75m3-6h.75m-.75 3h.75m-.75 3h.75M6.75 21v-3.375c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125V21M3 3h12m-.75 4.5H21m-3.75 3.75h.008v.008h-.008v-.008zm0 3h.008v.008h-.008v-.008zm0 3h.008v.008h-.008v-.008z"
                  />
                </svg>
              </div>
              <div>
                <div className="text-sm font-semibold text-[var(--text-primary)]">
                  Development Concept
                </div>
                <div className="text-xs text-[var(--text-muted)]">
                  Local concept of completed {maxUnits}-unit {typeLabel}
                </div>
              </div>
            </div>
            <span className="shrink-0 rounded-full border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-700 transition-colors group-hover:bg-amber-100 dark:border-amber-700 dark:bg-amber-950/50 dark:text-amber-400">
              Generate
            </span>
          </motion.button>
        )}

        {/* Loading skeleton */}
        {isLoading && (
          <motion.div
            key="loading"
            {...fadeUp}
            transition={springGentle}
            className="p-4 sm:p-5"
          >
            <div className="mb-3 h-4 w-48 rounded-md animate-shimmer" />
            <div className="aspect-[16/9] w-full rounded-xl animate-shimmer" />
            <div className="mt-3 h-3 w-32 rounded animate-shimmer" />
          </motion.div>
        )}

        {/* Error state */}
        {error && !isLoading && (
          <motion.div
            key="error"
            {...fadeUp}
            transition={springGentle}
            className="flex items-center justify-between gap-3 p-4"
          >
            <span className="text-sm text-red-600">{error}</span>
            <button onClick={handleGenerate} className="text-xs text-amber-700 underline">
              Retry
            </button>
          </motion.div>
        )}

        {/* Result */}
        {imageBase64 && !isLoading && (
          <motion.div
            key="image"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={springGentle}
          >
            <div className="relative overflow-hidden">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={`data:image/png;base64,${imageBase64}`}
                alt={`Concept render of ${maxUnits}-unit ${typeLabel} at ${address}`}
                className="h-auto w-full object-cover"
              />
              <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 to-transparent px-4 py-4">
                <p className="text-xs font-semibold text-white">{address}</p>
                <p className="text-xs text-white/70">
                  {maxUnits} units · {zoningDistrict} · local concept · {municipality}
                </p>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
