"use client";

import { AnimatePresence, motion } from "framer-motion";
import {
  Calendar,
  ChevronLeft,
  FileText,
  History,
  Mail,
  MessageSquare,
  Phone,
  RefreshCw,
  Send,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import type { DealData, OutreachActivityData } from "@/lib/api";
import { getDeal, logOutreach, deleteDeal, transitionDeal } from "@/lib/api";
import { fadeUp, springGentle } from "@/lib/motion";

const TABS = [
  { key: "overview", label: "Overview", icon: FileText },
  { key: "outreach", label: "Outreach", icon: MessageSquare },
  { key: "history", label: "History", icon: History },
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
  won: "Won",
  lost: "Lost",
};

function formatCurrency(n?: number): string {
  if (n == null || n === 0) return "—";
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(0)}K`;
  return `$${n.toLocaleString()}`;
}

export default function DealDetailPage() {
  const { dealId } = useParams<{ dealId: string }>();
  const router = useRouter();

  const [deal, setDeal] = useState<DealData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<string>("overview");
  const [showLogActivity, setShowLogActivity] = useState(false);

  const fetchDeal = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getDeal(dealId);
      setDeal(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load deal");
    } finally {
      setLoading(false);
    }
  }, [dealId]);

  useEffect(() => {
    fetchDeal();
  }, [fetchDeal]);

  const handleDelete = async () => {
    if (!confirm("Archive this deal? It will be moved to archived.")) return;
    try {
      await deleteDeal(dealId);
      router.push("/deals");
    } catch (err) {
      alert(err instanceof Error ? err.message : "Delete failed");
    }
  };

  const handleTransition = async (toStage: string) => {
    try {
      await transitionDeal(dealId, toStage);
      await fetchDeal();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Transition failed");
    }
  };

  if (loading) {
    return (
      <main className="min-h-full bg-[var(--bg-primary)] px-4 py-6 sm:px-6 lg:px-10">
        <div className="mx-auto max-w-6xl space-y-6">
          <div className="h-24 rounded-2xl animate-shimmer" />
          <div className="grid grid-cols-3 gap-4">
            <div className="h-32 rounded-2xl animate-shimmer" />
            <div className="h-32 rounded-2xl animate-shimmer" />
            <div className="h-32 rounded-2xl animate-shimmer" />
          </div>
        </div>
      </main>
    );
  }

  if (error || !deal) {
    return (
      <main className="min-h-full bg-[var(--bg-primary)] px-4 py-6 sm:px-6 lg:px-10">
        <div className="mx-auto max-w-6xl">
          <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400">
            {error || "Deal not found"}
            <button onClick={fetchDeal} className="ml-3 font-semibold underline">
              Retry
            </button>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-full bg-[var(--bg-primary)] px-4 py-6 sm:px-6 lg:px-10">
      <div className="mx-auto max-w-6xl space-y-6">
        {/* Header */}
        <motion.div
          className="flex flex-wrap items-start justify-between gap-4"
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={springGentle}
        >
          <div className="space-y-1">
            <Link
              href="/deals"
              className="inline-flex items-center gap-1 text-xs font-medium text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
            >
              <ChevronLeft className="h-3.5 w-3.5" />
              Back to pipeline
            </Link>
            <h1 className="text-2xl font-semibold text-[var(--text-primary)]">{deal.title}</h1>
            <p className="text-sm text-[var(--text-muted)]">{deal.property_address}</p>
          </div>
          <div className="flex items-center gap-3">
            <span
              className={`rounded-full px-3 py-1 text-xs font-semibold ${
                deal.status === "active"
                  ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-400"
                  : "bg-stone-100 text-stone-700 dark:bg-stone-800 dark:text-stone-400"
              }`}
            >
              {STAGE_LABELS[deal.stage] || deal.stage}
            </span>
            <button
              onClick={handleDelete}
              className="flex h-9 items-center gap-1.5 rounded-xl border border-[var(--border)] px-3 text-xs font-medium text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Archive
            </button>
          </div>
        </motion.div>

        {/* Metrics */}
        <motion.div
          className="grid grid-cols-2 gap-4 sm:grid-cols-4"
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ ...springGentle, delay: 0.05 }}
        >
          <MetricCard label="Asking Price" value={formatCurrency(deal.asking_price)} highlight />
          <MetricCard label="Offer Price" value={formatCurrency(deal.offer_price)} />
          <MetricCard
            label="Feasibility"
            value={deal.feasibility_score ? `${Math.round(deal.feasibility_score * 100)}%` : "—"}
          />
          <MetricCard
            label="Max Units"
            value={deal.max_units_residential ? String(deal.max_units_residential) : "—"}
          />
        </motion.div>

        {/* Tabs */}
        <div className="flex items-center gap-1 border-b border-[var(--border-soft)]">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.key;
            return (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-medium transition-colors ${
                  isActive
                    ? "border-amber-500 text-amber-600"
                    : "border-transparent text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
                }`}
              >
                <Icon className="h-4 w-4" />
                {tab.label}
              </button>
            );
          })}
        </div>

        {/* Tab content */}
        <AnimatePresence mode="wait">
          {activeTab === "overview" && (
            <OverviewTab key="overview" deal={deal} onTransition={handleTransition} />
          )}
          {activeTab === "outreach" && (
            <OutreachTab
              key="outreach"
              deal={deal}
              onRefresh={fetchDeal}
              onLogActivity={() => setShowLogActivity(true)}
            />
          )}
          {activeTab === "history" && <HistoryTab key="history" deal={deal} />}
        </AnimatePresence>
      </div>

      {/* Log Activity modal */}
      <AnimatePresence>
        {showLogActivity && (
          <LogActivityModal
            dealId={deal.id}
            onClose={() => setShowLogActivity(false)}
            onLogged={fetchDeal}
          />
        )}
      </AnimatePresence>
    </main>
  );
}

function MetricCard({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div
      className={`rounded-2xl border border-[var(--border-soft)] p-4 ${
        highlight ? "bg-amber-50 dark:bg-amber-950/20" : "bg-[var(--bg-surface)]"
      }`}
    >
      <div className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-muted)]">{label}</div>
      <div className={`mt-1 text-xl font-bold ${highlight ? "text-amber-700 dark:text-amber-400" : "text-[var(--text-primary)]"}`}>
        {value}
      </div>
    </div>
  );
}

function OverviewTab({ deal, onTransition }: { deal: DealData; onTransition: (stage: string) => void }) {
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
  const next = transitions[deal.stage] ?? [];

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={springGentle}
      className="grid gap-6 lg:grid-cols-[1fr_0.4fr]"
    >
      <div className="space-y-6">
        {/* Property Details */}
        <div className="rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-surface)] p-5">
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">Property Details</h3>
          <div className="mt-4 grid grid-cols-2 gap-4">
            <div>
              <div className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-muted)]">Owner</div>
              <div className="mt-0.5 text-sm text-[var(--text-primary)]">{deal.owner_name || "—"}</div>
            </div>
            <div>
              <div className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-muted)]">Email</div>
              <div className="mt-0.5 text-sm text-[var(--text-primary)]">{deal.owner_email || "—"}</div>
            </div>
            <div>
              <div className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-muted)]">Phone</div>
              <div className="mt-0.5 text-sm text-[var(--text-primary)]">{deal.owner_phone || "—"}</div>
            </div>
            <div>
              <div className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-muted)]">Deal Type</div>
              <div className="mt-0.5 text-sm text-[var(--text-primary)]">{deal.deal_type}</div>
            </div>
          </div>
        </div>

        {/* Quick Actions */}
        <div className="rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-surface)] p-5">
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">Quick Actions</h3>
          <div className="mt-4 flex flex-wrap gap-3">
            {next.map((stage) => (
              <button
                key={stage}
                onClick={() => onTransition(stage)}
                className="flex items-center gap-2 rounded-xl bg-amber-50 px-4 py-2 text-sm font-medium text-amber-700 transition-colors hover:bg-amber-100 dark:bg-amber-900/20 dark:text-amber-400"
              >
                <RefreshCw className="h-3.5 w-3.5" />
                Move to {STAGE_LABELS[stage] || stage}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Sidebar */}
      <div className="space-y-4">
        <div className="rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-surface)] p-5">
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">Deal Info</h3>
          <div className="mt-3 space-y-3 text-sm">
            <div className="flex justify-between">
              <span className="text-[var(--text-muted)]">ID</span>
              <span className="font-mono text-[var(--text-secondary)]">{deal.id.slice(0, 8)}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[var(--text-muted)]">Source</span>
              <span className="text-[var(--text-secondary)]">{deal.source}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-[var(--text-muted)]">Created</span>
              <span className="text-[var(--text-secondary)]">
                {deal.created_at ? new Date(deal.created_at).toLocaleDateString() : "—"}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-[var(--text-muted)]">Updated</span>
              <span className="text-[var(--text-secondary)]">
                {deal.updated_at ? new Date(deal.updated_at).toLocaleDateString() : "—"}
              </span>
            </div>
          </div>
        </div>
      </div>
    </motion.div>
  );
}

function OutreachTab({
  deal,
  onRefresh,
  onLogActivity,
}: {
  deal: DealData;
  onRefresh: () => void;
  onLogActivity: () => void;
}) {
  const activities = deal.outreach_activities || [];

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={springGentle}
      className="space-y-4"
    >
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-[var(--text-primary)]">
          Outreach Activity ({activities.length})
        </h3>
        <button
          onClick={onLogActivity}
          className="flex items-center gap-2 rounded-xl bg-amber-600 px-4 py-2 text-sm font-semibold text-white hover:bg-amber-700"
        >
          <Send className="h-3.5 w-3.5" />
          Log Activity
        </button>
      </div>

      {activities.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-[var(--border-soft)] bg-[var(--bg-surface)]/50 p-8 text-center">
          <p className="text-sm text-[var(--text-muted)]">No outreach activity logged yet.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {activities.map((activity) => (
            <ActivityCard key={activity.id} activity={activity} />
          ))}
        </div>
      )}
    </motion.div>
  );
}

function ActivityCard({ activity }: { activity: OutreachActivityData }) {
  const icons = {
    email: Mail,
    call: Phone,
    meeting: Calendar,
  };
  const Icon = icons[activity.activity_type] || MessageSquare;

  return (
    <div className="flex items-start gap-4 rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-surface)] p-4">
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--bg-primary)]">
        <Icon className="h-5 w-5 text-[var(--text-muted)]" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium capitalize text-[var(--text-primary)]">
            {activity.activity_type}
          </span>
          <span className="text-xs text-[var(--text-muted)]">
            {activity.created_at ? new Date(activity.created_at).toLocaleDateString() : ""}
          </span>
        </div>
        {activity.subject && <p className="mt-0.5 text-sm text-[var(--text-secondary)]">{activity.subject}</p>}
        {activity.call_outcome && (
          <div className="mt-1 flex items-center gap-2">
            <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-700">
              {activity.call_outcome}
            </span>
            {activity.sentiment && (
              <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-medium text-amber-700">
                {activity.sentiment}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function HistoryTab({ deal }: { deal: DealData }) {
  const history = deal.stage_history || [];

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={springGentle}
      className="space-y-4"
    >
      {history.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-[var(--border-soft)] bg-[var(--bg-surface)]/50 p-8 text-center">
          <p className="text-sm text-[var(--text-muted)]">No stage transitions yet.</p>
        </div>
      ) : (
        <div className="relative space-y-0">
          {history.map((h, i) => (
            <div key={h.id} className="flex gap-4 pb-6">
              <div className="flex flex-col items-center">
                <div className="h-3 w-3 rounded-full bg-amber-500" />
                {i < history.length - 1 && <div className="mt-2 h-full w-px bg-[var(--border-soft)]" />}
              </div>
              <div className="pb-2">
                <p className="text-sm font-medium text-[var(--text-primary)]">
                  {STAGE_LABELS[h.from_stage] || h.from_stage} → {STAGE_LABELS[h.to_stage] || h.to_stage}
                </p>
                <p className="mt-0.5 text-xs text-[var(--text-muted)]">
                  {h.transitioned_at ? new Date(h.transitioned_at).toLocaleString() : "—"}
                  {h.transitioned_by_user_id && ` · by ${h.transitioned_by_user_id}`}
                </p>
              </div>
            </div>
          ))}
        </div>
      )}
    </motion.div>
  );
}

function LogActivityModal({
  dealId,
  onClose,
  onLogged,
}: {
  dealId: string;
  onClose: () => void;
  onLogged: () => void;
}) {
  const [type, setType] = useState<"email" | "call" | "meeting">("call");
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState({
    subject: "",
    body: "",
    call_outcome: "interested",
    call_duration_seconds: "",
    sentiment: "positive",
    to_name: "",
    to_address: "",
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await logOutreach(dealId, {
        activity_type: type,
        subject: form.subject || undefined,
        body: form.body || undefined,
        call_outcome: type === "call" ? form.call_outcome : undefined,
        call_duration_seconds: form.call_duration_seconds ? parseInt(form.call_duration_seconds) : undefined,
        sentiment: type === "call" ? form.sentiment : undefined,
        to_name: form.to_name || undefined,
        to_address: form.to_address || undefined,
      });
      onLogged();
      onClose();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to log activity");
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
        initial={{ scale: 0.95 }}
        animate={{ scale: 1 }}
        exit={{ scale: 0.95 }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-semibold text-[var(--text-primary)]">Log Activity</h2>

        <div className="mt-4 flex gap-2">
          {(["call", "email", "meeting"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setType(t)}
              className={`rounded-xl px-4 py-2 text-sm font-medium capitalize ${
                type === t
                  ? "bg-amber-600 text-white"
                  : "bg-[var(--bg-primary)] text-[var(--text-secondary)] hover:bg-[var(--bg-surface-raised)]"
              }`}
            >
              {t}
            </button>
          ))}
        </div>

        <form onSubmit={handleSubmit} className="mt-5 space-y-4">
          {type === "email" && (
            <>
              <input
                placeholder="Subject"
                value={form.subject}
                onChange={(e) => setForm({ ...form, subject: e.target.value })}
                className="w-full rounded-xl border border-[var(--border)] bg-[var(--input-bg)] px-3 py-2.5 text-sm outline-none focus:border-amber-500/60"
              />
              <textarea
                placeholder="Body"
                rows={4}
                value={form.body}
                onChange={(e) => setForm({ ...form, body: e.target.value })}
                className="w-full rounded-xl border border-[var(--border)] bg-[var(--input-bg)] px-3 py-2.5 text-sm outline-none focus:border-amber-500/60"
              />
            </>
          )}

          {type === "call" && (
            <>
              <div className="grid grid-cols-2 gap-3">
                <select
                  value={form.call_outcome}
                  onChange={(e) => setForm({ ...form, call_outcome: e.target.value })}
                  className="rounded-xl border border-[var(--border)] bg-[var(--input-bg)] px-3 py-2.5 text-sm outline-none focus:border-amber-500/60"
                >
                  <option value="interested">Interested</option>
                  <option value="not_interested">Not Interested</option>
                  <option value="no_answer">No Answer</option>
                  <option value="voicemail">Voicemail</option>
                  <option value="follow_up">Follow Up</option>
                </select>
                <select
                  value={form.sentiment}
                  onChange={(e) => setForm({ ...form, sentiment: e.target.value })}
                  className="rounded-xl border border-[var(--border)] bg-[var(--input-bg)] px-3 py-2.5 text-sm outline-none focus:border-amber-500/60"
                >
                  <option value="positive">Positive</option>
                  <option value="neutral">Neutral</option>
                  <option value="negative">Negative</option>
                </select>
              </div>
              <input
                type="number"
                placeholder="Duration (seconds)"
                value={form.call_duration_seconds}
                onChange={(e) => setForm({ ...form, call_duration_seconds: e.target.value })}
                className="w-full rounded-xl border border-[var(--border)] bg-[var(--input-bg)] px-3 py-2.5 text-sm outline-none focus:border-amber-500/60"
              />
            </>
          )}

          {type === "meeting" && (
            <>
              <input
                placeholder="Meeting subject"
                value={form.subject}
                onChange={(e) => setForm({ ...form, subject: e.target.value })}
                className="w-full rounded-xl border border-[var(--border)] bg-[var(--input-bg)] px-3 py-2.5 text-sm outline-none focus:border-amber-500/60"
              />
              <textarea
                placeholder="Notes"
                rows={3}
                value={form.body}
                onChange={(e) => setForm({ ...form, body: e.target.value })}
                className="w-full rounded-xl border border-[var(--border)] bg-[var(--input-bg)] px-3 py-2.5 text-sm outline-none focus:border-amber-500/60"
              />
            </>
          )}

          <div className="flex justify-end gap-3 pt-2">
            <button type="button" onClick={onClose} className="rounded-xl px-5 py-2.5 text-sm text-[var(--text-muted)]">
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="rounded-xl bg-amber-600 px-6 py-2.5 text-sm font-semibold text-white hover:bg-amber-700 disabled:opacity-50"
            >
              {submitting ? "Saving..." : "Save Activity"}
            </button>
          </div>
        </form>
      </motion.div>
    </motion.div>
  );
}
