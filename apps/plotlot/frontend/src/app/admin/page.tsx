"use client";

import { useState, useEffect, useCallback } from "react";

interface MunicipalityData {
  municipality: string;
  county: string;
  chunk_count: number;
  section_count: number;
  first_ingested: string | null;
  last_ingested: string | null;
  avg_chunk_length: number;
  min_chunk_length: number;
  max_chunk_length: number;
}

interface DataQualityResponse {
  total_municipalities: number;
  total_chunks: number;
  municipalities: MunicipalityData[];
  error?: string;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function AdminPage() {
  const [data, setData] = useState<DataQualityResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`${API_BASE}/api/v1/admin/data-quality`);
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const json = await resp.json();
      if (json.error) throw new Error(json.error);
      setData(json);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  return (
    <div className="mx-auto max-w-4xl px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[var(--text-primary)]">Data Dashboard</h1>
          <p className="mt-1 text-sm text-stone-500">Municipality coverage and ingestion status</p>
        </div>
        <button
          onClick={fetchData}
          disabled={loading}
          className="rounded-lg border border-[var(--border)] bg-[var(--bg-surface)] px-4 py-2 text-sm font-medium text-stone-600 shadow-sm transition-colors hover:bg-[var(--bg-surface-raised)] disabled:opacity-40"
        >
          {loading ? "Loading..." : "Refresh"}
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-950/30 dark:text-red-400">
          {error}
        </div>
      )}

      {data && data.municipalities && (
        <>
          {/* Summary cards */}
          <div className="mb-6 grid grid-cols-3 gap-4">
            <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] p-4 shadow-sm">
              <div className="text-xs font-medium uppercase tracking-wider text-stone-500">Municipalities</div>
              <div className="mt-1 text-2xl font-bold text-[var(--text-primary)]">{data.total_municipalities ?? 0}</div>
              <div className="mt-0.5 text-xs text-stone-500">of 88 discoverable</div>
            </div>
            <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] p-4 shadow-sm">
              <div className="text-xs font-medium uppercase tracking-wider text-stone-500">Total Chunks</div>
              <div className="mt-1 text-2xl font-bold text-[var(--text-primary)]">{(data.total_chunks ?? 0).toLocaleString()}</div>
              <div className="mt-0.5 text-xs text-stone-500">ordinance text chunks</div>
            </div>
            <div className="rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] p-4 shadow-sm">
              <div className="text-xs font-medium uppercase tracking-wider text-stone-500">Coverage</div>
              <div className="mt-1 text-2xl font-bold text-amber-700 dark:text-amber-400">
                {Math.round(((data.total_municipalities ?? 0) / 88) * 100)}%
              </div>
              <div className="mt-0.5 text-xs text-stone-500">of Municode municipalities</div>
            </div>
          </div>

          {/* Municipality table */}
          <div className="overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] shadow-sm">
            <table className="min-w-full text-sm">
              <thead className="bg-[var(--bg-surface-raised)]">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-stone-500">Municipality</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-stone-500">County</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-stone-500">Chunks</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-stone-500">Sections</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-wider text-stone-500">Last Ingested</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100 dark:divide-stone-800">
                {data.municipalities.map((m) => (
                  <tr key={m.municipality} className="hover:bg-[var(--bg-surface-raised)]">
                    <td className="px-4 py-3 font-medium text-[var(--text-primary)]">{m.municipality}</td>
                    <td className="px-4 py-3 text-stone-500">{m.county}</td>
                    <td className="px-4 py-3 text-right font-mono text-[var(--text-secondary)]">{m.chunk_count.toLocaleString()}</td>
                    <td className="px-4 py-3 text-right font-mono text-[var(--text-secondary)]">{m.section_count}</td>
                    <td className="px-4 py-3 text-right text-xs text-stone-500">
                      {m.last_ingested
                        ? new Date(m.last_ingested).toLocaleDateString()
                        : "N/A"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {loading && !data && (
        <div className="flex items-center justify-center py-20">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-stone-300 border-t-amber-600" />
        </div>
      )}
    </div>
  );
}
