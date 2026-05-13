"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { springGentle, fadeUp } from "@/lib/motion";

interface PropertyFlyoverVideoProps {
  address: string;
  lat?: number | null;
  lng?: number | null;
  municipality: string;
}

export default function PropertyFlyoverVideo({
  address,
  lat,
  lng,
  municipality,
}: PropertyFlyoverVideoProps) {
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);

  const handleGenerate = async () => {
    setIsLoading(true);
    setError(null);
    setProgress(0);

    // Tick progress toward 90% over ~60s while Veo 3 generates
    const interval = setInterval(() => {
      setProgress((prev) => (prev < 90 ? prev + 1.4 : prev));
    }, 1000);

    try {
      const resp = await fetch("/api/video/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ address, lat, lng, municipality }),
      });
      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({}));
        throw new Error(errData.error || `Generation failed: ${resp.status}`);
      }
      const data = await resp.json();
      setProgress(100);
      setVideoUrl(data.videoUrl);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Aerial flyover generation failed");
    } finally {
      clearInterval(interval);
      setIsLoading(false);
    }
  };

  return (
    <div
      className="overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)]"
      style={{ boxShadow: "var(--shadow-card)" }}
    >
      <AnimatePresence mode="wait">
        {/* CTA */}
        {!videoUrl && !isLoading && !error && (
          <motion.button
            key="cta"
            {...fadeUp}
            transition={springGentle}
            onClick={handleGenerate}
            className="group flex w-full items-center justify-between gap-3 p-4 text-left transition-colors hover:bg-[var(--bg-surface-raised)] sm:p-5"
          >
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-stone-100 dark:bg-stone-800">
                <svg
                  className="h-5 w-5 text-stone-600 dark:text-stone-400"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                  strokeWidth={1.5}
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d="M15.75 10.5l4.72-4.72a.75.75 0 011.28.53v11.38a.75.75 0 01-1.28.53l-4.72-4.72M4.5 18.75h9a2.25 2.25 0 002.25-2.25v-9a2.25 2.25 0 00-2.25-2.25h-9A2.25 2.25 0 002.25 7.5v9a2.25 2.25 0 002.25 2.25z"
                  />
                </svg>
              </div>
              <div>
                <div className="text-sm font-semibold text-[var(--text-primary)]">
                  Aerial Property Flyover
                </div>
                <div className="text-xs text-[var(--text-muted)]">
                  AI-generated cinematic drone footage · Veo 3 · ~60s generation
                </div>
              </div>
            </div>
            <span className="shrink-0 rounded-full border border-[var(--border)] bg-[var(--bg-surface)] px-3 py-1.5 text-xs font-medium text-[var(--text-secondary)] transition-colors group-hover:border-[var(--border-hover)] group-hover:text-[var(--text-primary)]">
              Generate
            </span>
          </motion.button>
        )}

        {/* Loading */}
        {isLoading && (
          <motion.div
            key="loading"
            {...fadeUp}
            transition={springGentle}
            className="p-4 sm:p-5"
          >
            <div className="mb-3 flex items-center gap-2">
              <svg className="h-4 w-4 animate-spin text-amber-600" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <span className="text-sm font-medium text-[var(--text-secondary)]">
                Generating aerial flyover…
              </span>
              <span className="ml-auto text-xs tabular-nums text-[var(--text-muted)]">
                {Math.round(progress)}%
              </span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-[var(--bg-surface-raised)]">
              <motion.div
                className="h-full rounded-full bg-amber-500"
                animate={{ width: `${progress}%` }}
                transition={{ type: "spring", stiffness: 60, damping: 15 }}
              />
            </div>
            <div className="mt-4 aspect-[16/9] w-full rounded-xl animate-shimmer" />
            <p className="mt-3 text-center text-xs text-[var(--text-muted)]">
              Veo 3 is rendering cinematic footage of {address}
            </p>
          </motion.div>
        )}

        {/* Error */}
        {error && !isLoading && !videoUrl && (
          <motion.div
            key="error"
            {...fadeUp}
            transition={springGentle}
            className="flex items-center justify-between gap-3 p-4"
          >
            <span className="text-sm text-red-600">{error}</span>
            <button
              onClick={handleGenerate}
              className="shrink-0 text-xs text-amber-700 underline"
            >
              Retry
            </button>
          </motion.div>
        )}

        {/* Video */}
        {videoUrl && !isLoading && (
          <motion.div
            key="video"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={springGentle}
          >
            <video
              src={videoUrl}
              autoPlay
              loop
              muted
              playsInline
              className="w-full rounded-t-2xl"
            />
            <div className="flex items-center gap-2 px-4 py-2.5 text-xs text-[var(--text-muted)]">
              <svg className="h-3 w-3 text-amber-500" viewBox="0 0 20 20" fill="currentColor">
                <path d="M2 6a2 2 0 012-2h6a2 2 0 012 2v8a2 2 0 01-2 2H4a2 2 0 01-2-2V6zM14.553 7.106A1 1 0 0014 8v4a1 1 0 00.553.894l2 1A1 1 0 0018 13V7a1 1 0 00-1.447-.894l-2 1z" />
              </svg>
              AI-generated aerial flyover · powered by Veo 3
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
