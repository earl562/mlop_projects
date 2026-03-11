"use client";

function Pulse({ className }: { className: string }) {
  return <div className={`animate-pulse rounded bg-[var(--bg-surface-raised)] ${className}`} />;
}

export function ReportSkeleton() {
  return (
    <div className="w-full space-y-6 rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] p-4 shadow-sm sm:p-6">
      {/* Header skeleton */}
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0 flex-1 space-y-2">
          <Pulse className="h-6 w-3/4" />
          <Pulse className="h-4 w-1/3" />
        </div>
        <div className="flex shrink-0 flex-col items-end gap-2">
          <Pulse className="h-6 w-16 rounded-full" />
          <Pulse className="h-8 w-16 rounded-lg" />
        </div>
      </div>

      {/* Map skeleton */}
      <Pulse className="h-[200px] w-full rounded-lg sm:h-[250px]" />

      {/* Zoning district skeleton */}
      <div className="flex items-center gap-3">
        <Pulse className="h-8 w-24" />
        <Pulse className="h-4 w-48" />
      </div>

      {/* Summary skeleton */}
      <div className="space-y-2 rounded-lg bg-[var(--bg-surface-raised)] p-4">
        <Pulse className="h-4 w-full" />
        <Pulse className="h-4 w-5/6" />
        <Pulse className="h-4 w-4/6" />
      </div>

      {/* Density breakdown skeleton */}
      <div className="space-y-3">
        <Pulse className="h-4 w-32" />
        <div className="rounded-lg border border-[var(--border)] p-4">
          <Pulse className="h-12 w-24 mx-auto" />
          <div className="mt-4 space-y-3">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="space-y-1">
                <div className="flex justify-between">
                  <Pulse className="h-3 w-24" />
                  <Pulse className="h-3 w-12" />
                </div>
                <Pulse className="h-2 w-full rounded-full" />
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Dimensional standards skeleton */}
      <div className="space-y-2">
        <Pulse className="h-4 w-40" />
        <div className="space-y-1">
          {[1, 2, 3, 4, 5].map((i) => (
            <div key={i} className="flex justify-between border-b border-[var(--border)] py-2">
              <Pulse className="h-3 w-24" />
              <Pulse className="h-3 w-16" />
            </div>
          ))}
        </div>
      </div>

      {/* Setbacks skeleton */}
      <div className="space-y-2">
        <Pulse className="h-4 w-20" />
        <div className="grid grid-cols-3 gap-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="rounded-lg bg-[var(--bg-surface-raised)] p-3 text-center">
              <Pulse className="mx-auto h-3 w-10" />
              <Pulse className="mx-auto mt-2 h-5 w-12" />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function SatelliteMapSkeleton() {
  return (
    <div className="relative h-[200px] w-full overflow-hidden rounded-lg border border-[var(--border)] sm:h-[250px]">
      <div className="absolute inset-0 animate-pulse bg-[var(--bg-surface-raised)]" />
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="flex flex-col items-center gap-2">
          <svg
            className="h-6 w-6 animate-spin text-[var(--text-muted)]"
            viewBox="0 0 24 24"
            fill="none"
          >
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          <span className="text-xs text-[var(--text-muted)]">Loading map...</span>
        </div>
      </div>
    </div>
  );
}
