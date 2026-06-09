"use client";

import { motion } from "framer-motion";
import { Calendar, Filter, Mail, Phone, Send } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import type { OutreachActivityData } from "@/lib/api";
import { getOutreachMetrics, listDeals, logOutreach } from "@/lib/api";
import { fadeUp, springGentle } from "@/lib/motion";

export default function OutreachPage() {
  const [activities, setActivities] = useState<OutreachActivityData[]>([]);
  const [metrics, setMetrics] = useState({ total_activities: 0, emails: 0, calls: 0, meetings: 0, interested_calls: 0 });
  const [loading, setLoading] = useState(true);

  const [filterType, setFilterType] = useState<string>("");
  const [showCompose, setShowCompose] = useState(false);

  const fetchOutreach = useCallback(async () => {
    setLoading(true);
    try {
      const [m, deals] = await Promise.all([getOutreachMetrics(), listDeals()]);
      setMetrics(m);
      const allActivities = deals.flatMap((d) => d.outreach_activities || []);
      setActivities(allActivities.filter(Boolean));
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchOutreach();
  }, [fetchOutreach]);

  const filtered = useMemo(() => {
    let list = activities;
    if (filterType) {
      list = list.filter((a) => a.activity_type === filterType);
    }
    return list.sort((a, b) => ((b.created_at ?? "") > (a.created_at ?? "") ? 1 : -1));
  }, [activities, filterType]);

  const responseRate = useMemo(() => {
    const total = metrics.calls;
    if (total === 0) return 0;
    return Math.round((metrics.interested_calls / total) * 100);
  }, [metrics]);

  return (
    <main className="min-h-full bg-[var(--bg-primary)] px-4 py-6 sm:px-6 lg:px-10">
      <div className="mx-auto max-w-6xl space-y-6">
        {/* Header */}
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-xs font-semibold uppercase tracking-[0.24em] text-[var(--brand)]">
              Outreach
            </h1>
            <p className="mt-2 font-display text-3xl font-semibold tracking-tight text-[var(--text-primary)]">
              Activity Log
            </p>
          </div>
          <motion.button
            onClick={() => setShowCompose(true)}
            className="flex items-center gap-2 rounded-xl bg-amber-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-amber-700"
            whileHover={{ y: -1 }}
            whileTap={{ scale: 0.97 }}
          >
            <Send className="h-4 w-4" />
            Compose Email
          </motion.button>
        </div>

        {/* Metrics */}
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
          <MetricCard label="Total Activities" value={metrics.total_activities} />
          <MetricCard label="Emails" value={metrics.emails} icon={<Mail className="h-4 w-4" />} />
          <MetricCard label="Calls" value={metrics.calls} icon={<Phone className="h-4 w-4" />} />
          <MetricCard label="Meetings" value={metrics.meetings} icon={<Calendar className="h-4 w-4" />} />
          <MetricCard label="Response Rate" value={`${responseRate}%`} highlight />
        </div>

        {/* Filters */}
        <div className="flex items-center gap-3">
          <Filter className="h-4 w-4 text-[var(--text-muted)]" />
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="h-10 rounded-xl border border-[var(--border)] bg-[var(--bg-surface)] px-3 text-sm text-[var(--text-primary)] outline-none focus:border-amber-500/60"
          >
            <option value="">All types</option>
            <option value="email">Email</option>
            <option value="call">Call</option>
            <option value="meeting">Meeting</option>
          </select>
        </div>

        {/* Feed */}
        {loading ? (
          <div className="space-y-3">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-20 rounded-2xl animate-shimmer" />
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-[var(--border-soft)] bg-[var(--bg-surface)]/50 p-8 text-center">
            <p className="text-sm text-[var(--text-muted)]">No outreach activity found.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {filtered.map((activity, i) => (
              <ActivityRow key={activity.id} activity={activity} index={i} />
            ))}
          </div>
        )}
      </div>

      {/* Compose modal would go here */}
    </main>
  );
}

function MetricCard({ label, value, icon, highlight }: { label: string; value: string | number; icon?: React.ReactNode; highlight?: boolean }) {
  return (
    <div className={`rounded-2xl border border-[var(--border-soft)] p-4 ${highlight ? "bg-amber-50 dark:bg-amber-950/20" : "bg-[var(--bg-surface)]"}`}>
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-muted)]">{label}</span>
        {icon && <span className="text-[var(--text-muted)]">{icon}</span>}
      </div>
      <div className={`mt-1 text-2xl font-bold ${highlight ? "text-amber-700 dark:text-amber-400" : "text-[var(--text-primary)]"}`}>
        {value}
      </div>
    </div>
  );
}

function ActivityRow({ activity, index }: { activity: OutreachActivityData; index: number }) {
  const icons = {
    email: <Mail className="h-4 w-4" />,
    call: <Phone className="h-4 w-4" />,
    meeting: <Calendar className="h-4 w-4" />,
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ ...springGentle, delay: index * 0.03 }}
      className="flex items-center gap-4 rounded-2xl border border-[var(--border-soft)] bg-[var(--bg-surface)] p-4"
    >
      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-[var(--bg-primary)] text-[var(--text-muted)]">
        {icons[activity.activity_type as keyof typeof icons] || <Mail className="h-4 w-4" />}
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
        {activity.subject && <p className="text-sm text-[var(--text-secondary)] line-clamp-1">{activity.subject}</p>}
        {activity.call_outcome && (
          <div className="mt-1 flex items-center gap-2">
            <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-medium text-emerald-700">
              {activity.call_outcome}
            </span>
          </div>
        )}
      </div>
    </motion.div>
  );
}
