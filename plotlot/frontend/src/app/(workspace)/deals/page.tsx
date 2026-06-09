"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Filter, Plus, Search } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { DealData } from "@/lib/api";
import { createDeal, listDeals, transitionDeal } from "@/lib/api";
import { fadeUp, springGentle, staggerContainer, staggerItem } from "@/lib/motion";

const PIPELINE_STAGES = [
  "lead",
  "contacted",
  "qualified",
  "site_visit_scheduled",
  "site_visit_completed",
  "underwriting",
  "loi_submitted",
  "loi_accepted",
  "psa_submitted",
  "psa_executed",
  "due_diligence",
  "closing",
] as const;

const STAGE_LABELS: Record<string, string> = {
  lead: "Lead",
  contacted: "Contacted",
  qualified: "Qualified",
  site_visit_scheduled: "Site Visit Scheduled",
  site_visit_completed: "Site Visit Completed",
  underwriting: "Underwriting",
  loi_submitted: "LOI Submitted",
  loi_accepted: "LOI Accepted",
  psa_submitted: "PSA Submitted",
  psa_executed: "PSA Executed",
  due_diligence: "Due Diligence",
  closing: "Closing",
};

function formatCurrency(n?: number): string {
  if (n == null || n === 0) return "—";
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(0)}K`;
  return `$${n.toLocaleString()}`;
}

function daysInStage(stageEnteredAt?: string): number {
  if (!stageEnteredAt) return 0;
  const entered = new Date(stageEnteredAt);
  const now = new Date();
  return Math.max(0, Math.floor((now.getTime() - entered.getTime()) / 86400000));
}

export default function DealsPage() {
  const [deals, setDeals] = useState<DealData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [showCreate, setShowCreate] = useState(false);
  const [filterStage, setFilterStage] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState("");
  const [sortBy, setSortBy] = useState<"updated" | "created" | "price">("updated");

  const fetchDeals = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listDeals();
      setDeals(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load deals");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDeals();
  }, [fetchDeals]);

  const filteredDeals = useMemo(() => {
    let list = deals.filter((d) => !d.is_deleted);
    if (filterStage) {
      list = list.filter((d) => d.stage === filterStage);
    }
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      list = list.filter(
        (d) =>
          d.title.toLowerCase().includes(q) ||
          d.property_address.toLowerCase().includes(q) ||
          (d.owner_name && d.owner_name.toLowerCase().includes(q)),
      );
    }
    list.sort((a, b) => {
      if (sortBy === "price") return (b.asking_price ?? 0) - (a.asking_price ?? 0);
      if (sortBy === "created") {
        return (b.created_at ?? "").localeCompare(a.created_at ?? "");
      }
      return (b.updated_at ?? "").localeCompare(a.updated_at ?? "");
    });
    return list;
  }, [deals, filterStage, searchQuery, sortBy]);

  const stageCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const stage of PIPELINE_STAGES) counts[stage] = 0;
    for (const d of deals) {
      if (!d.is_deleted) {
        counts[d.stage] = (counts[d.stage] ?? 0) + 1;
      }
    }
    return counts;
  }, [deals]);

  const handleTransition = useCallback(
    async (dealId: string, toStage: string) => {
      try {
        await transitionDeal(dealId, toStage);
        await fetchDeals();
      } catch (err) {
        alert(err instanceof Error ? err.message : "Transition failed");
      }
    },
    [fetchDeals],
  );

  return (
    <main className="min-h-full bg-[var(--bg-primary)] px-4 py-6 sm:px-6 lg:px-10">
      <section className="mx-auto max-w-[1600px]">
        {/* Header */}
        <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-xs font-semibold uppercase tracking-[0.24em] text-[var(--brand)]">
              Acquisition Pipeline
            </h1>
            <p className="mt-2 font-display text-3xl font-semibold tracking-tight text-[var(--text-primary)]">
              {filteredDeals.length} deal{filteredDeals.length !== 1 ? "s" : ""}
            </p>
          </div>
          <div className="flex items-center gap-3">
            {/* Search */}
            <div className="relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[var(--text-muted)]" />
              <input
                type="text"
                placeholder="Search deals..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="h-10 w-64 rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] pl-9 pr-4 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:border-amber-500/60"
              />
            </div>
            {/* Filter */}
            <select
              value={filterStage}
              onChange={(e) => setFilterStage(e.target.value)}
              className="h-10 rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] px-3 text-sm text-[var(--text-primary)] focus:outline-none focus:border-amber-500/60"
            >
              <option value="">All stages</option>
              {PIPELINE_STAGES.map((s) => (
                <option key={s} value={s}>
                  {STAGE_LABELS[s]}
                </option>
              ))}
            </select>
            {/* Sort */}
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as any)}
              className="h-10 rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] px-3 text-sm text-[var(--text-primary)] focus:outline-none focus:border-amber-500/60"
            >
              <option value="updated">Recently updated</option>
              <option value="created">Newest first</option>
              <option value="price">Highest price</option>
            </select>
            {/* Create */}
            <motion.button
              onClick={() => setShowCreate(true)}
              className="flex h-10 items-center gap-2 rounded-xl bg-amber-600 px-5 text-sm font-semibold text-white hover:bg-amber-700"
              whileHover={{ y: -1 }}
              whileTap={{ scale: 0.97 }}
            >
              <Plus className="h-4 w-4" />
              New Deal
            </motion.button>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="mb-6 rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400">
            {error}
            <button onClick={fetchDeals} className="ml-3 font-semibold underline">
              Retry
            </button>
          </div>
        )}

        {/* Board */}
        {loading ? (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
            {Array.from({ length: 12 }).map((_, i) => (
              <div key={i} className="space-y-3">
                <div className="h-8 rounded-lg animate-shimmer" />
                <div className="h-32 rounded-xl animate-shimmer" />
                <div className="h-32 rounded-xl animate-shimmer" />
              </div>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6">
            {PIPELINE_STAGES.map((stage) => {
              const stageDeals = filteredDeals.filter((d) => d.stage === stage);
              return (
                <PipelineColumn
                  key={stage}
                  stage={stage}
                  label={STAGE_LABELS[stage]}
                  count={stageCounts[stage] ?? 0}
                  deals={stageDeals}
                  onTransition={handleTransition}
                />
              );
            })}
          </div>
        )}
      </section>

      {/* Create Modal */}
      <AnimatePresence>
        {showCreate && <CreateDealModal onClose={() => setShowCreate(false)} onCreated={fetchDeals} />}
      </AnimatePresence>
    </main>
  );
}

function PipelineColumn({
  stage,
  label,
  count,
  deals,
  onTransition,
}: {
  stage: string;
  label: string;
  count: number;
  deals: DealData[];
  onTransition: (dealId: string, toStage: string) => void;
}) {
  const nextStages = useMemo(() => {
    const transitions: Record<string, string[]> = {
      lead: ["contacted"],
      contacted: ["qualified"],
      qualified: ["site_visit_scheduled"],
      site_visit_scheduled: ["site_visit_completed"],
      site_visit_completed: ["underwriting"],
      underwriting: ["loi_submitted"],
      loi_submitted: ["loi_accepted"],
      loi_accepted: ["psa_submitted"],
      psa_submitted: ["psa_executed"],
      psa_executed: ["due_diligence"],
      due_diligence: ["closing"],
      closing: ["won"],
    };
    return transitions[stage] ?? [];
  }, [stage]);

  return (
    <div className="flex flex-col gap-3">
      {/* Column header */}
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
          {label}
        </h3>
        <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-semibold text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
          {count}
        </span>
      </div>

      {/* Cards */}
      <motion.div
        className="flex flex-col gap-3"
        variants={staggerContainer}
        initial="hidden"
        animate="visible"
      >
        {deals.length === 0 ? (
          <div className="rounded-xl border border-dashed border-[var(--border-soft)] bg-[var(--bg-surface)]/50 p-4 text-center">
            <p className="text-xs text-[var(--text-muted)]">No deals</p>
          </div>
        ) : (
          deals.map((deal, i) => (
            <DealCard
              key={deal.id}
              deal={deal}
              index={i}
              nextStages={nextStages}
              onTransition={onTransition}
            />
          ))
        )}
      </motion.div>
    </div>
  );
}

function DealCard({
  deal,
  index,
  nextStages,
  onTransition,
}: {
  deal: DealData;
  index: number;
  nextStages: string[];
  onTransition: (dealId: string, toStage: string) => void;
}) {
  const [showActions, setShowActions] = useState(false);

  return (
    <motion.div
      variants={staggerItem}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ ...springGentle, delay: index * 0.03 }}
      className="group relative rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-surface)] p-4 shadow-[var(--shadow-card)] transition-all hover:shadow-md hover:-translate-y-0.5"
      onMouseEnter={() => setShowActions(true)}
      onMouseLeave={() => setShowActions(false)}
    >
      <Link href={`/deals/${deal.id}`} className="block">
        <div className="space-y-2">
          {/* Title */}
          <h4 className="text-sm font-semibold text-[var(--text-primary)] line-clamp-1">
            {deal.title}
          </h4>

          {/* Address */}
          <p className="text-xs text-[var(--text-muted)] line-clamp-1">
            {deal.property_address}
          </p>

          {/* Price & Owner */}
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold text-amber-600 dark:text-amber-400">
              {formatCurrency(deal.asking_price)}
            </span>
            <span className="text-[11px] text-[var(--text-muted)]">
              {deal.owner_name || "Unknown owner"}
            </span>
          </div>

          {/* Days in stage */}
          <div className="flex items-center justify-between border-t border-[var(--border-soft)] pt-2">
            <span className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-muted)]">
              {daysInStage(deal.stage_entered_at)}d in stage
            </span>
            {deal.feasibility_score != null && deal.feasibility_score > 0 && (
              <span className="rounded-full bg-emerald-50 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400">
                {Math.round(deal.feasibility_score * 100)}% feasible
              </span>
            )}
          </div>
        </div>
      </Link>

      {/* Quick transition actions */}
      <AnimatePresence>
        {showActions && nextStages.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            className="mt-3 flex flex-wrap gap-1.5 border-t border-[var(--border-soft)] pt-3"
          >
            {nextStages.map((nextStage) => (
              <button
                key={nextStage}
                onClick={(e) => {
                  e.preventDefault();
                  onTransition(deal.id, nextStage);
                }}
                className="rounded-full bg-[var(--bg-primary)] px-2.5 py-1 text-[10px] font-medium text-[var(--text-secondary)] transition-colors hover:bg-amber-50 hover:text-amber-700 dark:hover:bg-amber-900/20 dark:hover:text-amber-400"
              >
                → {STAGE_LABELS[nextStage]}
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

function CreateDealModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState({
    title: "",
    property_address: "",
    asking_price: "",
    owner_name: "",
    owner_email: "",
    workspace_id: "ws_default",
    project_id: "prj_default",
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await createDeal({
        ...form,
        asking_price: form.asking_price ? parseFloat(form.asking_price) : undefined,
      });
      onCreated();
      onClose();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to create deal");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <motion.div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onClick={onClose}
    >
      <motion.div
        className="w-full max-w-lg rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-surface)] p-6 shadow-xl"
        initial={{ scale: 0.95, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.95, opacity: 0 }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold text-[var(--text-primary)]">New Deal</h2>
        <form onSubmit={handleSubmit} className="mt-5 space-y-4">
          <div>
            <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">
              Title
            </label>
            <input
              required
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              className="mt-1 w-full rounded-xl border border-[var(--border)] bg-[var(--input-bg)] px-3 py-2.5 text-sm text-[var(--text-primary)] outline-none focus:border-amber-500/60"
              placeholder="Acme Development Site"
            />
          </div>
          <div>
            <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">
              Property Address
            </label>
            <input
              required
              value={form.property_address}
              onChange={(e) => setForm({ ...form, property_address: e.target.value })}
              className="mt-1 w-full rounded-xl border border-[var(--border)] bg-[var(--input-bg)] px-3 py-2.5 text-sm text-[var(--text-primary)] outline-none focus:border-amber-500/60"
              placeholder="123 Main St, Miami, FL 33101"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">
                Asking Price
              </label>
              <input
                type="number"
                value={form.asking_price}
                onChange={(e) => setForm({ ...form, asking_price: e.target.value })}
                className="mt-1 w-full rounded-xl border border-[var(--border)] bg-[var(--input-bg)] px-3 py-2.5 text-sm text-[var(--text-primary)] outline-none focus:border-amber-500/60"
                placeholder="3000000"
              />
            </div>
            <div>
              <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">
                Owner Name
              </label>
              <input
                value={form.owner_name}
                onChange={(e) => setForm({ ...form, owner_name: e.target.value })}
                className="mt-1 w-full rounded-xl border border-[var(--border)] bg-[var(--input-bg)] px-3 py-2.5 text-sm text-[var(--text-primary)] outline-none focus:border-amber-500/60"
                placeholder="Jane Smith LLC"
              />
            </div>
          </div>
          <div>
            <label className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">
              Owner Email
            </label>
            <input
              type="email"
              value={form.owner_email}
              onChange={(e) => setForm({ ...form, owner_email: e.target.value })}
              className="mt-1 w-full rounded-xl border border-[var(--border)] bg-[var(--input-bg)] px-3 py-2.5 text-sm text-[var(--text-primary)] outline-none focus:border-amber-500/60"
              placeholder="jane@example.com"
            />
          </div>
          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-xl px-5 py-2.5 text-sm font-medium text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="rounded-xl bg-amber-600 px-6 py-2.5 text-sm font-semibold text-white hover:bg-amber-700 disabled:opacity-50"
            >
              {submitting ? "Creating..." : "Create Deal"}
            </button>
          </div>
        </form>
      </motion.div>
    </motion.div>
  );
}
