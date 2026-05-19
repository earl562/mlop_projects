"use client";

import { useState, useEffect, useCallback } from "react";
import { listPortfolio, deleteFromPortfolio, type SavedAnalysis } from "@/lib/api";

interface PortfolioPanelProps {
  onSelectAnalysis?: (analysis: SavedAnalysis) => void;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export default function PortfolioPanel({ onSelectAnalysis }: PortfolioPanelProps) {
  const [items, setItems] = useState<SavedAnalysis[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listPortfolio();
      setItems(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load portfolio");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setDeletingId(id);
    try {
      await deleteFromPortfolio(id);
      setItems((prev) => prev.filter((item) => item.id !== id));
    } catch {
      // ignore — item stays in list
    } finally {
      setDeletingId(null);
    }
  };

  if (loading) {
    return (
      <div className="space-y-2 px-1 py-2">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-16 animate-shimmer rounded-xl" />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center gap-3 px-1 py-8">
        <p className="text-center text-xs text-[var(--text-muted)]">{error}</p>
        <button
          onClick={load}
          className="rounded-full border border-[var(--border)] px-4 py-1.5 text-xs font-medium text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)]"
        >
          Retry
        </button>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 px-1 py-10">
        <svg className="h-8 w-8 text-[var(--text-muted)] opacity-40" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 21h16.5M4.5 3h15M5.25 3v18m13.5-18v18M9 6.75h1.5m-1.5 3h1.5m-1.5 3h1.5m3-6H15m-1.5 3H15m-1.5 3H15M9 21v-3.375c0-.621.504-1.125 1.125-1.125h3.75c.621 0 1.125.504 1.125 1.125V21" />
        </svg>
        <p className="text-xs text-[var(--text-muted)]">No saved analyses yet</p>
        <p className="text-center text-[10px] text-[var(--text-muted)] opacity-70">
          Run an analysis and save it to build your portfolio
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-1.5 px-1 py-2">
      {items.map((item) => (
        <div
          key={item.id}
          onClick={() => onSelectAnalysis?.(item)}
          className="group relative cursor-pointer rounded-xl border border-[var(--border-soft)] bg-[var(--bg-surface)] px-3 py-2.5 transition-all hover:border-[var(--border)] hover:bg-[var(--bg-surface-raised)]"
        >
          <div className="pr-6">
            <p className="truncate text-xs font-medium text-[var(--text-primary)]">
              {item.address}
            </p>
            <div className="mt-1 flex items-center gap-2">
              {item.zoning_district && (
                <span className="rounded-full bg-[var(--bg-inset)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--text-muted)]">
                  {item.zoning_district}
                </span>
              )}
              {item.max_units != null && (
                <span className="rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 dark:bg-amber-950/50 dark:text-amber-400">
                  {item.max_units} units
                </span>
              )}
              <span className="ml-auto text-[10px] text-[var(--text-muted)]">
                {formatDate(item.saved_at)}
              </span>
            </div>
          </div>
          <button
            onClick={(e) => handleDelete(item.id, e)}
            disabled={deletingId === item.id}
            className="absolute right-2 top-2.5 flex h-5 w-5 items-center justify-center rounded-md text-[var(--text-muted)] opacity-0 transition-opacity group-hover:opacity-100 hover:text-[var(--danger)]"
            aria-label="Remove from portfolio"
          >
            {deletingId === item.id ? (
              <svg className="h-3 w-3 animate-spin" viewBox="0 0 24 24" fill="none">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            ) : (
              <svg className="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
              </svg>
            )}
          </button>
        </div>
      ))}
    </div>
  );
}
