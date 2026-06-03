"use client";

import { motion } from "framer-motion";
import { springGentle, staggerContainer, staggerItem } from "@/lib/motion";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface FloodZoneInfo {
  zone: string;
  zone_subtype: string;
  in_sfha: boolean;
  risk_level: string;
  description: string;
}

interface WetlandInfo {
  wetland_type: string;
  acres: number;
}

export interface SiteRiskData {
  flood_zone: FloodZoneInfo | null;
  wetlands: WetlandInfo[];
  has_wetlands: boolean;
  overall_risk: string;
  risk_flags: string[];
  data_sources: string[];
}

interface SiteRiskCardProps {
  siteRisk: SiteRiskData;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const RISK_COLORS = {
  high: {
    badge: "bg-red-100 text-red-700 border-red-200 dark:bg-red-950/30 dark:text-red-400 dark:border-red-800",
    bar: "bg-red-500",
    icon: "text-red-500",
    border: "border-l-red-500",
  },
  moderate: {
    badge: "bg-amber-100 text-amber-700 border-amber-200 dark:bg-amber-950/30 dark:text-amber-400 dark:border-amber-800",
    bar: "bg-amber-500",
    icon: "text-amber-500",
    border: "border-l-amber-400",
  },
  low: {
    badge: "bg-emerald-100 text-emerald-700 border-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-400 dark:border-emerald-800",
    bar: "bg-emerald-500",
    icon: "text-emerald-500",
    border: "border-l-emerald-400",
  },
  minimal: {
    badge: "bg-emerald-100 text-emerald-700 border-emerald-200 dark:bg-emerald-950/30 dark:text-emerald-400 dark:border-emerald-800",
    bar: "bg-emerald-500",
    icon: "text-emerald-500",
    border: "border-l-emerald-400",
  },
  unknown: {
    badge: "bg-stone-100 text-stone-600 border-stone-200 dark:bg-stone-800/30 dark:text-stone-400 dark:border-stone-700",
    bar: "bg-stone-400",
    icon: "text-stone-400",
    border: "border-l-stone-400",
  },
};

function riskColors(level: string) {
  return RISK_COLORS[level as keyof typeof RISK_COLORS] ?? RISK_COLORS.unknown;
}

function RiskBadge({ level, label }: { level: string; label: string }) {
  const c = riskColors(level);
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wide ${c.badge}`}
    >
      {label}
    </span>
  );
}

// Shield icon
function ShieldIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  );
}

// Warning triangle icon
function WarnIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 20 20" fill="currentColor">
      <path
        fillRule="evenodd"
        d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z"
        clipRule="evenodd"
      />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function SiteRiskCard({ siteRisk }: SiteRiskCardProps) {
  const overallColors = riskColors(siteRisk.overall_risk);

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={springGentle}
      className="rounded-2xl border border-[var(--border)] bg-[var(--bg-surface)] p-4 sm:p-6"
      style={{ boxShadow: "var(--shadow-card)" }}
    >
      {/* Header */}
      <div className="mb-4 flex items-center justify-between gap-4">
        <div className="flex items-center gap-2.5">
          <ShieldIcon className={`h-5 w-5 shrink-0 ${overallColors.icon}`} />
          <div>
            <span className="section-pill">Site Risk</span>
            <p className="mt-0.5 text-xs text-[var(--text-muted)]">
              FEMA Flood · USFWS Wetlands
            </p>
          </div>
        </div>
        <RiskBadge
          level={siteRisk.overall_risk}
          label={`${siteRisk.overall_risk.charAt(0).toUpperCase() + siteRisk.overall_risk.slice(1)} Risk`}
        />
      </div>

      {/* Flood zone row */}
      <motion.div
        variants={staggerContainer}
        initial="hidden"
        animate="visible"
        className="space-y-3"
      >
        {siteRisk.flood_zone && (
          <motion.div
            variants={staggerItem}
            className={`rounded-lg border-l-4 bg-[var(--bg-subtle)] p-3 ${riskColors(siteRisk.flood_zone.risk_level).border}`}
          >
            <div className="mb-1 flex items-center justify-between gap-2">
              <span className="text-sm font-semibold text-[var(--text-primary)]">
                FEMA Flood Zone{" "}
                <code className="rounded bg-[var(--bg-surface)] px-1.5 py-0.5 font-mono text-xs">
                  {siteRisk.flood_zone.zone}
                </code>
              </span>
              <RiskBadge
                level={siteRisk.flood_zone.risk_level}
                label={siteRisk.flood_zone.risk_level}
              />
            </div>
            <p className="text-xs text-[var(--text-muted)]">
              {siteRisk.flood_zone.description}
            </p>
            {siteRisk.flood_zone.in_sfha && (
              <p className="mt-1.5 text-xs font-medium text-red-600 dark:text-red-400">
                ⚠ SFHA — flood insurance required for federally-backed mortgages
              </p>
            )}
          </motion.div>
        )}

        {/* Wetlands row */}
        <motion.div
          variants={staggerItem}
          className={`rounded-lg border-l-4 bg-[var(--bg-subtle)] p-3 ${
            siteRisk.has_wetlands
              ? "border-l-amber-400"
              : "border-l-emerald-400"
          }`}
        >
          <div className="mb-1 flex items-center justify-between gap-2">
            <span className="text-sm font-semibold text-[var(--text-primary)]">
              NWI Wetlands
            </span>
            <RiskBadge
              level={siteRisk.has_wetlands ? "moderate" : "minimal"}
              label={siteRisk.has_wetlands ? "Detected" : "None detected"}
            />
          </div>
          {siteRisk.has_wetlands ? (
            <ul className="mt-1 space-y-0.5">
              {siteRisk.wetlands.map((w, i) => (
                <li key={i} className="text-xs text-[var(--text-muted)]">
                  {w.wetland_type}
                  {w.acres > 0 ? ` — ${w.acres.toFixed(2)} acres` : ""}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-[var(--text-muted)]">
              No wetlands found within ~100m of parcel
            </p>
          )}
        </motion.div>

        {/* Risk flags */}
        {siteRisk.risk_flags.length > 0 && (
          <motion.div variants={staggerItem} className="space-y-1.5">
            {siteRisk.risk_flags.map((flag, i) => (
              <div key={i} className="flex items-start gap-2">
                <WarnIcon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-500" />
                <p className="text-xs text-[var(--text-secondary)]">{flag}</p>
              </div>
            ))}
          </motion.div>
        )}

        {/* Data sources */}
        {siteRisk.data_sources.length > 0 && (
          <motion.p variants={staggerItem} className="text-[10px] text-[var(--text-muted)]">
            Sources: {siteRisk.data_sources.join(" · ")}
          </motion.p>
        )}
      </motion.div>
    </motion.div>
  );
}
