"use client";

import { motion } from "framer-motion";
import type { DealAnalysisData } from "@/lib/api";
import { springGentle, staggerContainer, staggerItem, fadeUp } from "@/lib/motion";
import {
  TrendingUp,
  DollarSign,
  AlertTriangle,
  CheckCircle2,
  Target,
  BarChart3,
  ShieldAlert,
  FileText,
} from "lucide-react";

interface DealDashboardProps {
  dealAnalysis: DealAnalysisData | null;
  loading?: boolean;
}

// ---------------------------------------------------------------------------
// Rating configuration
// ---------------------------------------------------------------------------

const RATING_CONFIG: Record<string, { label: string; palette: string; icon: typeof TrendingUp }> = {
  "Strong Buy": {
    label: "Strong Buy",
    palette: "emerald",
    icon: TrendingUp,
  },
  Buy: {
    label: "Buy",
    palette: "brand",
    icon: TrendingUp,
  },
  Hold: {
    label: "Hold",
    palette: "amber",
    icon: Target,
  },
  Pass: {
    label: "Pass",
    palette: "red",
    icon: ShieldAlert,
  },
};

function ratingClasses(rating: string): { bg: string; text: string; border: string; glow: string } {
  const p = RATING_CONFIG[rating]?.palette ?? "stone";

  if (p === "brand") {
    return {
      bg: "bg-[var(--brand-subtle)]",
      text: "text-[var(--brand)]",
      border: "border-[var(--brand-soft-border)]",
      glow: "shadow-[0_0_24px_var(--brand-glow)]",
    };
  }

  if (p === "emerald") {
    return {
      bg: "bg-[var(--success-subtle)]",
      text: "text-[var(--success)]",
      border: "border-emerald-500/30",
      glow: "shadow-[0_0_24px_rgba(4,120,87,0.15)]",
    };
  }

  if (p === "amber") {
    return {
      bg: "bg-[var(--warning-subtle)]",
      text: "text-[var(--warning)]",
      border: "border-amber-500/30",
      glow: "shadow-[0_0_24px_rgba(217,119,6,0.15)]",
    };
  }

  return {
    bg: "bg-[var(--danger-subtle)]",
    text: "text-[var(--danger)]",
    border: "border-red-500/30",
    glow: "shadow-[0_0_24px_rgba(220,38,38,0.15)]",
  };
}

// ---------------------------------------------------------------------------
// Formatting helpers
// ---------------------------------------------------------------------------

function fmtMoney(n: number | null | undefined): string {
  if (n == null || n === 0) return "—";
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function fmtPct(n: number | null | undefined, decimals = 1): string {
  if (n == null || n === 0) return "—";
  return `${n.toFixed(decimals)}%`;
}

function fmtMult(n: number | null | undefined): string {
  if (n == null || n === 0) return "—";
  return `${n.toFixed(2)}x`;
}

// ---------------------------------------------------------------------------
// Metric tile — reusable metric display
// ---------------------------------------------------------------------------

interface MetricTileProps {
  label: string;
  value: string;
  subtext?: string;
  icon: React.ReactNode;
  highlight?: boolean;
  valueClassName?: string;
}

function MetricTile({ label, value, subtext, icon, highlight, valueClassName }: MetricTileProps) {
  return (
    <div
      className={`relative overflow-hidden rounded-xl border p-4 transition-colors ${
        highlight
          ? "bg-[var(--brand-subtle)] border-[var(--brand-soft-border)]"
          : "bg-[var(--bg-surface)] border-[var(--border-soft)]"
      }`}
    >
      {highlight && (
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.04]"
          style={{ background: "radial-gradient(ellipse at 50% 0%, var(--brand) 0%, transparent 70%)" }}
        />
      )}
      <div className="relative">
        <div className="mb-2 flex items-center gap-1.5">
          <span className="text-[var(--text-muted)]">{icon}</span>
          <span className="text-[10px] font-semibold uppercase tracking-[0.06em] text-[var(--text-muted)]">
            {label}
          </span>
        </div>
        <div
          className={`text-xl font-bold tracking-tight sm:text-2xl ${
            valueClassName ?? (highlight ? "text-[var(--brand)]" : "text-[var(--text-primary)]")
          }`}
        >
          {value}
        </div>
        {subtext && (
          <div className="mt-0.5 text-[10px] font-medium text-[var(--text-muted)]">
            {subtext}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Skeleton — loading state
// ---------------------------------------------------------------------------

function DashboardSkeleton() {
  return (
    <div className="space-y-4">
      {/* Rating skeleton */}
      <div className="animate-shimmer h-[104px] rounded-2xl" />

      {/* Offers skeleton — 2 columns */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="animate-shimmer h-[88px] rounded-xl" />
        <div className="animate-shimmer h-[88px] rounded-xl" />
      </div>

      {/* Metrics skeleton — 3 columns */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="animate-shimmer h-[80px] rounded-xl" />
        <div className="animate-shimmer h-[80px] rounded-xl" />
        <div className="animate-shimmer h-[80px] rounded-xl" />
      </div>

      {/* Deal breakers skeleton */}
      <div className="animate-shimmer h-[120px] rounded-xl" />

      {/* Summary skeleton */}
      <div className="animate-shimmer h-[80px] rounded-xl" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Rating badge — hero section
// ---------------------------------------------------------------------------

function RatingHero({ rating }: { rating: string }) {
  const config = RATING_CONFIG[rating] ?? RATING_CONFIG.Pass;
  const cls = ratingClasses(rating);
  const Icon = config.icon;

  return (
    <motion.div
      {...fadeUp}
      transition={springGentle}
      className={`relative overflow-hidden rounded-2xl border p-5 sm:p-6 ${cls.border} ${cls.bg}`}
    >
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.06]"
        style={{ background: "radial-gradient(ellipse at 30% 20%, currentColor 0%, transparent 70%)" }}
      />
      <div className="relative flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <span
            className={`flex h-10 w-10 items-center justify-center rounded-xl border ${cls.border} ${cls.bg}`}
          >
            <Icon className={`h-5 w-5 ${cls.text}`} />
          </span>
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
              Investment Rating
            </div>
            <div className={`mt-1 font-display text-2xl font-bold tracking-tight sm:text-3xl ${cls.text}`}>
              {config.label}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-1.5 self-start rounded-full border px-3 py-1.5"
          style={{ borderColor: "var(--border)", backgroundColor: "var(--bg-surface)" }}
        >
          <div className={`h-2 w-2 rounded-full ${cls.text.replace("text-", "bg-")}`} />
          <span className="text-[11px] font-medium text-[var(--text-secondary)] tabular-nums">
            {rating}
          </span>
        </div>
      </div>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Offer cards — max offer + recommended
// ---------------------------------------------------------------------------

function OfferSection({ maxOffer, recommended }: { maxOffer: number; recommended: number }) {
  return (
    <motion.div
      variants={staggerContainer}
      initial="hidden"
      animate="visible"
      className="grid grid-cols-1 gap-3 sm:grid-cols-2"
    >
      {/* Max offer */}
      <motion.div variants={staggerItem}>
        <MetricTile
          label="Max Offer Price"
          value={fmtMoney(maxOffer)}
          subtext={maxOffer > 0 ? "Residual land value ceiling" : undefined}
          icon={<DollarSign className="h-4 w-4" />}
          highlight
        />
      </motion.div>

      {/* Recommended offer */}
      <motion.div variants={staggerItem}>
        <MetricTile
          label="Recommended Offer"
          value={fmtMoney(recommended)}
          subtext={recommended > 0 ? "Conservative entry point" : undefined}
          icon={<Target className="h-4 w-4" />}
        />
      </motion.div>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Deal metric tiles — CoC, DSCR, cap rate
// ---------------------------------------------------------------------------

function MetricsSection({ metrics }: { metrics: DealAnalysisData["metrics"] }) {
  const entries = [
    {
      label: "Cash-on-Cash",
      value: fmtPct(metrics?.levered_cash_on_cash),
      subtext: "Year-1 levered",
      icon: <BarChart3 className="h-4 w-4" />,
      important: (metrics?.levered_cash_on_cash ?? 0) >= 8,
    },
    {
      label: "DSCR",
      value: metrics?.dscr ? metrics.dscr.toFixed(2) : "—",
      subtext: "Debt service coverage",
      icon: <CheckCircle2 className="h-4 w-4" />,
      important: (metrics?.dscr ?? 0) >= 1.25,
    },
    {
      label: "Cap Rate",
      value: fmtPct(metrics?.cap_rate),
      subtext: "Stabilized NOI / cost",
      icon: <TrendingUp className="h-4 w-4" />,
      important: (metrics?.cap_rate ?? 0) >= 6,
    },
  ];

  return (
    <motion.div
      variants={staggerContainer}
      initial="hidden"
      animate="visible"
      className="grid grid-cols-1 gap-3 sm:grid-cols-3"
    >
      {entries.map(({ label, value, subtext, icon, important }, i) => (
        <motion.div key={label} variants={staggerItem}>
          <MetricTile
            label={label}
            value={value}
            subtext={subtext}
            icon={icon}
            highlight={important}
            valueClassName={important ? "text-[var(--brand)]" : "text-[var(--text-primary)]"}
          />
        </motion.div>
      ))}
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Deal breakers panel
// ---------------------------------------------------------------------------

function DealBreakers({ items }: { items: string[] }) {
  if (items.length === 0) {
    return (
      <motion.div
        {...fadeUp}
        transition={{ ...springGentle, delay: 0.2 }}
        className="flex items-center gap-3 rounded-xl border border-[var(--border-soft)] bg-[var(--bg-surface)] p-5"
      >
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-[var(--success-subtle)]">
          <CheckCircle2 className="h-4 w-4 text-[var(--success)]" />
        </span>
        <div>
          <div className="text-sm font-semibold text-[var(--text-primary)]">No Deal Breakers</div>
          <div className="text-[11px] text-[var(--text-muted)]">This deal passes all screening criteria.</div>
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      {...fadeUp}
      transition={{ ...springGentle, delay: 0.2 }}
      className="overflow-hidden rounded-xl border border-red-500/25 bg-[var(--danger-subtle)]"
    >
      <div className="flex items-center gap-2 border-b border-red-500/15 px-4 py-3">
        <AlertTriangle className="h-4 w-4 text-[var(--danger)]" />
        <span className="text-xs font-semibold uppercase tracking-[0.06em] text-[var(--danger)]">
          Deal Breakers
        </span>
        <span className="ml-auto rounded-full bg-red-500/15 px-2 py-0.5 text-[11px] font-medium text-[var(--danger)] tabular-nums">
          {items.length}
        </span>
      </div>

      <ul className="divide-y divide-red-500/10">
        {items.map((breaker, i) => (
          <motion.li
            key={i}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ ...springGentle, delay: 0.35 + i * 0.06 }}
            className="flex items-start gap-2.5 px-4 py-3"
          >
            <ShieldAlert className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[var(--danger)]" />
            <span className="text-sm text-[var(--text-primary)]">{breaker}</span>
          </motion.li>
        ))}
      </ul>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Summary section
// ---------------------------------------------------------------------------

function SummarySection({ summary }: { summary: string }) {
  if (!summary) {
    return (
      <motion.div
        {...fadeUp}
        transition={{ ...springGentle, delay: 0.3 }}
        className="rounded-xl border border-[var(--border-soft)] bg-[var(--bg-surface)] p-5"
      >
        <div className="flex items-center gap-2 text-[var(--text-muted)]">
          <FileText className="h-4 w-4" />
          <span className="text-sm">No summary available yet.</span>
        </div>
      </motion.div>
    );
  }

  return (
    <motion.div
      {...fadeUp}
      transition={{ ...springGentle, delay: 0.3 }}
      className="rounded-xl border border-[var(--border-soft)] bg-[var(--bg-surface)] p-5"
    >
      <div className="mb-3 flex items-center gap-2">
        <FileText className="h-4 w-4 text-[var(--text-muted)]" />
        <span className="text-[10px] font-semibold uppercase tracking-[0.08em] text-[var(--text-muted)]">
          Executive Summary
        </span>
      </div>
      <p className="text-sm leading-relaxed text-[var(--text-secondary)]">{summary}</p>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Empty state
// ---------------------------------------------------------------------------

function EmptyState() {
  return (
    <motion.div
      {...fadeUp}
      transition={springGentle}
      className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-[var(--border)] bg-[var(--bg-surface)] py-14"
    >
      <span className="flex h-12 w-12 items-center justify-center rounded-xl bg-[var(--bg-inset)]">
        <BarChart3 className="h-6 w-6 text-[var(--text-muted)]" />
      </span>
      <p className="mt-4 text-sm font-medium text-[var(--text-secondary)]">
        No deal analysis available
      </p>
      <p className="mt-1 text-xs text-[var(--text-muted)]">
        Run a full analysis to generate investment metrics.
      </p>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

export default function DealDashboard({ dealAnalysis, loading = false }: DealDashboardProps) {
  if (loading) return <DashboardSkeleton />;
  if (!dealAnalysis) return <EmptyState />;

  return (
    <div className="space-y-4">
      {/* Section label */}
      <div className="flex items-center gap-2">
        <span className="section-pill">Deal Analysis</span>
        <div className="gold-accent flex-1" />
      </div>

      {/* 1) Investment rating */}
      <RatingHero rating={dealAnalysis.investment_rating} />

      {/* 2) Max offer + recommended */}
      <OfferSection
        maxOffer={dealAnalysis.max_offer_price}
        recommended={dealAnalysis.recommended_offer}
      />

      {/* 3) Deal metrics */}
      <MetricsSection metrics={dealAnalysis.metrics} />

      {/* 4) Deal breakers */}
      <DealBreakers items={dealAnalysis.deal_breakers ?? []} />

      {/* 5) Summary */}
      <SummarySection summary={dealAnalysis.summary} />
    </div>
  );
}
