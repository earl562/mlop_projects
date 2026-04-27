"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import type { DealType } from "./DealTypeSelector";
import type { ZoningReportData, ComparableSaleData } from "@/lib/api";
import { springGentle, fadeUp } from "@/lib/motion";

interface DealHeroCardProps {
  report: ZoningReportData;
  dealType: DealType;
}

function MetricBox({ label, value, highlight, subtext }: { label: string; value: string; highlight?: boolean; subtext?: string }) {
  return (
    <div className={`rounded-xl p-3 sm:p-4 ${highlight ? "bg-amber-50 dark:bg-amber-950/40" : "bg-[var(--bg-surface-raised)]"}`}>
      <div className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-muted)]">{label}</div>
      <div className={`mt-1 text-lg font-bold sm:text-xl ${highlight ? "text-amber-700 dark:text-amber-400" : "text-[var(--text-primary)]"}`}>
        {value}
      </div>
      {subtext && <div className="mt-0.5 text-[10px] text-[var(--text-muted)]">{subtext}</div>}
    </div>
  );
}

function MiniInput({ label, value, onChange, prefix, suffix, placeholder, min, max }: {
  label: string; value: string; onChange: (v: string) => void;
  prefix?: string; suffix?: string; placeholder?: string;
  min?: number; max?: number;
}) {
  const numVal = parseFloat(value.replace(/,/g, ""));
  const isInvalid = value !== "" && isNaN(numVal);
  const isOutOfRange = !isNaN(numVal) && value !== "" &&
    ((min !== undefined && numVal < min) || (max !== undefined && numVal > max));
  const hasError = isInvalid || isOutOfRange;

  return (
    <div className="space-y-1">
      <label className="text-[10px] font-medium uppercase tracking-wider text-[var(--text-muted)]">{label}</label>
      <div className={`flex items-center gap-1 rounded-lg border bg-[var(--bg-surface)] px-2 py-1.5 ${hasError ? "border-red-400" : "border-[var(--border)]"}`}>
        {prefix && <span className="text-xs text-[var(--text-muted)]">{prefix}</span>}
        <input
          type="text"
          inputMode="decimal"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full bg-transparent text-xs font-medium text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)]"
        />
        {suffix && <span className="text-xs text-[var(--text-muted)]">{suffix}</span>}
      </div>
      {isInvalid && <p className="text-[9px] text-red-500">Enter a number</p>}
      {isOutOfRange && !isInvalid && (
        <p className="text-[9px] text-red-500">
          {min !== undefined && max !== undefined ? `Must be ${min}–${max}` : min !== undefined ? `Min ${min}` : `Max ${max}`}
        </p>
      )}
    </div>
  );
}

function fmt(n: number | null | undefined, prefix = "$"): string {
  if (n == null || n === 0) return "N/A";
  return `${prefix}${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function fmtPct(n: number | null | undefined): string {
  if (n == null) return "N/A";
  return `${n.toFixed(1)}%`;
}

/** Calculate median days on market from comp sale dates */
function calcMedianDOM(comps: ComparableSaleData[]): number | null {
  const now = Date.now();
  const days = comps
    .map((c) => {
      if (!c.sale_date) return null;
      const d = new Date(c.sale_date);
      if (isNaN(d.getTime())) return null;
      return Math.round((now - d.getTime()) / 86400000);
    })
    .filter((d): d is number => d !== null && d >= 0)
    .sort((a, b) => a - b);

  if (days.length === 0) return null;
  const mid = Math.floor(days.length / 2);
  return days.length % 2 === 0 ? Math.round((days[mid - 1] + days[mid]) / 2) : days[mid];
}

// ---------------------------------------------------------------------------
// Staggered metric grid — shared by all hero types
// ---------------------------------------------------------------------------

function MetricGrid({ metrics }: { metrics: Array<{ label: string; value: string; highlight?: boolean; subtext?: string }> }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
      {metrics.map(({ label, value, highlight, subtext }, i) => (
        <motion.div
          key={label}
          {...fadeUp}
          transition={{ ...springGentle, delay: i * 0.05 }}
        >
          <MetricBox label={label} value={value} highlight={highlight} subtext={subtext} />
        </motion.div>
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Land Deal Hero
// ---------------------------------------------------------------------------

function LandDealHero({ report }: { report: ZoningReportData }) {
  const da = report.density_analysis;
  const pf = report.pro_forma;
  const maxUnits = da?.max_units ?? 0;
  const maxOffer = pf?.max_land_price ?? 0;
  const rlvPerDoor = maxUnits > 0 && maxOffer > 0 ? maxOffer / maxUnits : 0;
  const gdv = pf?.gross_development_value ?? 0;
  const totalCost = (pf?.hard_costs ?? 0) + (pf?.soft_costs ?? 0) + maxOffer;
  const devMargin = gdv > 0 ? ((gdv - totalCost) / gdv) * 100 : null;
  const governing = da?.governing_constraint?.replace(/_/g, " ") || "N/A";

  return (
    <MetricGrid
      metrics={[
        { label: "Max Units", value: maxUnits > 0 ? maxUnits.toString() : "N/A", highlight: true },
        { label: "Max Offer (RLV)", value: fmt(maxOffer), highlight: true },
        { label: "RLV / Door", value: fmt(rlvPerDoor) },
        { label: "Dev Margin", value: fmtPct(devMargin) },
        { label: "Governing", value: governing },
      ]}
    />
  );
}

// ---------------------------------------------------------------------------
// Wholesale Hero
// ---------------------------------------------------------------------------

function WholesaleHero({ report }: { report: ZoningReportData }) {
  const comp = report.comp_analysis;
  const adv = comp?.adv_per_unit ?? comp?.estimated_land_value ?? 0;
  const hasComps = adv > 0;
  const mao = hasComps ? adv * 0.7 : 0;
  const repairEst = hasComps ? adv * 0.1 : 0;
  const fee = hasComps ? Math.min(adv * 0.05, 15000) : 0;
  const dom = comp?.comparables ? calcMedianDOM(comp.comparables) : null;

  return (
    <MetricGrid
      metrics={[
        { label: "ARV", value: hasComps ? fmt(adv) : "No recent comps", highlight: hasComps },
        { label: "MAO (70%)", value: hasComps ? fmt(mao) : "No recent comps", highlight: hasComps },
        { label: "Repair Est.", value: hasComps ? fmt(repairEst) : "—", subtext: hasComps ? "~10% of ARV" : undefined },
        { label: "Assignment Fee", value: hasComps ? fmt(fee) : "—", subtext: hasComps ? "~5% cap $15K" : undefined },
        { label: "Comp DOM", value: dom !== null ? `${dom}d` : "No recent comps", subtext: dom !== null ? "median days" : undefined },
      ]}
    />
  );
}

// ---------------------------------------------------------------------------
// Creative Finance Hero
// ---------------------------------------------------------------------------

function CreativeFinanceHero({ report }: { report: ZoningReportData }) {
  const pr = report.property_record;
  const comp = report.comp_analysis;
  const mv = pr?.market_value ?? 0;
  const arv = comp?.adv_per_unit ?? comp?.estimated_land_value ?? 0;

  const [mortgageRate, setMortgageRate] = useState("");
  const [mortgageBalance, setMortgageBalance] = useState("");
  const [monthlyPayment, setMonthlyPayment] = useState("");

  const rate = parseFloat(mortgageRate) || 0;
  const balance = parseFloat(mortgageBalance.replace(/,/g, "")) || 0;
  const payment = parseFloat(monthlyPayment.replace(/,/g, "")) || 0;

  const currentMarketRate = 7.0;
  const rateSpread = rate > 0 ? currentMarketRate - rate : null;
  const equityCapture = mv > 0 && balance > 0 ? mv - balance : (arv > 0 && mv > 0 ? arv - mv : 0);
  const ltv = mv > 0 && balance > 0 ? (balance / mv) * 100 : (mv > 0 && arv > 0 ? (mv / arv) * 100 : null);

  const estMonthlyRent = arv > 0 ? arv * 0.008 : mv * 0.008;
  const monthlyCF = payment > 0 ? estMonthlyRent - payment : null;
  const cashInvested = equityCapture > 0 ? Math.min(equityCapture * 0.1, 10000) : 5000;
  const annualYield = monthlyCF !== null && cashInvested > 0 ? ((monthlyCF * 12) / cashInvested) * 100 : null;

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-2 rounded-xl border border-dashed border-[var(--border)] bg-[var(--bg-surface-raised)] p-3">
        <MiniInput label="Existing Rate" value={mortgageRate} onChange={setMortgageRate} suffix="%" placeholder="4.5" min={0} max={30} />
        <MiniInput label="Mortgage Bal." value={mortgageBalance} onChange={setMortgageBalance} prefix="$" placeholder="180,000" />
        <MiniInput label="Monthly Pmt" value={monthlyPayment} onChange={setMonthlyPayment} prefix="$" placeholder="1,200" />
      </div>
      <MetricGrid
        metrics={[
          {
            label: "Rate Spread",
            value: rateSpread !== null ? `${rateSpread.toFixed(1)}pp` : "Enter rate",
            highlight: rateSpread !== null && rateSpread > 0,
            subtext: rateSpread !== null ? `${rate}% vs ${currentMarketRate}% mkt` : undefined,
          },
          {
            label: "Equity Capture",
            value: equityCapture > 0 ? fmt(equityCapture) : "N/A",
            highlight: equityCapture > 0,
          },
          {
            label: "Monthly CF",
            value: monthlyCF !== null ? fmt(monthlyCF, monthlyCF >= 0 ? "$" : "-$") : "Enter pmt",
            highlight: monthlyCF !== null && monthlyCF > 0,
            subtext: monthlyCF !== null ? `rent ~${fmt(Math.round(estMonthlyRent))}` : undefined,
          },
          { label: "LTV", value: ltv !== null ? fmtPct(ltv) : "N/A" },
          {
            label: "Yield",
            value: annualYield !== null ? fmtPct(annualYield) : "Enter terms",
            highlight: annualYield !== null && annualYield > 15,
            subtext: annualYield !== null ? "annual CoC" : undefined,
          },
        ]}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Hybrid Hero
// ---------------------------------------------------------------------------

function HybridHero({ report }: { report: ZoningReportData }) {
  const da = report.density_analysis;
  const pf = report.pro_forma;
  const comp = report.comp_analysis;
  const pr = report.property_record;

  const [existingRate, setExistingRate] = useState("");
  const [mortgageBalance, setMortgageBalance] = useState("");
  const [monthlyPayment, setMonthlyPayment] = useState("");

  const maxUnits = da?.max_units ?? 0;
  const mv = pr?.market_value ?? 0;
  const arv = comp?.adv_per_unit ?? comp?.estimated_land_value ?? 0;
  const maxOffer = pf?.max_land_price ?? 0;

  const rate = parseFloat(existingRate) || 0;
  const balance = parseFloat(mortgageBalance.replace(/,/g, "")) || 0;
  const payment = parseFloat(monthlyPayment.replace(/,/g, "")) || 0;

  const currentMarketRate = 7.0;
  const newFinancingAmt = mv > 0 && balance > 0 ? mv - balance : maxOffer;
  const totalFinancing = balance + newFinancingAmt;
  const blendedRate =
    rate > 0 && totalFinancing > 0
      ? (rate * balance + currentMarketRate * newFinancingAmt) / totalFinancing
      : null;

  const cashToClose = balance > 0 ? Math.max(0, mv - balance) * 0.05 + 5000 : null;
  const baseValue = arv > 0 ? arv : mv;
  const estMonthlyRent = baseValue > 0 ? baseValue * 0.008 : null;
  const combinedCF = payment > 0 && estMonthlyRent !== null ? estMonthlyRent - payment : null;
  const totalEquity = mv > 0 && balance > 0 ? mv - balance : arv > 0 && mv > 0 ? arv - mv : 0;

  const exitPaths: string[] = [];
  if (maxUnits > 1) exitPaths.push("Develop");
  if (totalEquity > 0) exitPaths.push("Wholesale");
  if (combinedCF !== null && combinedCF > 0) exitPaths.push("Hold");
  if (arv > 0 && mv > 0 && arv > mv) exitPaths.push("Flip");
  if (rate > 0 && rate < currentMarketRate) exitPaths.push("Wrap");

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-2 rounded-xl border border-dashed border-[var(--border)] bg-[var(--bg-surface-raised)] p-3">
        <MiniInput label="Existing Rate" value={existingRate} onChange={setExistingRate} suffix="%" placeholder="4.5" min={0} max={30} />
        <MiniInput label="Mortgage Bal." value={mortgageBalance} onChange={setMortgageBalance} prefix="$" placeholder="180,000" />
        <MiniInput label="Monthly Pmt" value={monthlyPayment} onChange={setMonthlyPayment} prefix="$" placeholder="1,200" />
      </div>
      <MetricGrid
        metrics={[
          {
            label: "Blended Rate",
            value: blendedRate !== null ? fmtPct(blendedRate) : "Enter terms",
            highlight: blendedRate !== null && blendedRate < currentMarketRate,
            subtext: blendedRate !== null ? `vs ${currentMarketRate}% mkt` : undefined,
          },
          { label: "Cash to Close", value: cashToClose !== null ? fmt(cashToClose) : "Enter bal." },
          {
            label: "Combined CF",
            value: combinedCF !== null ? fmt(Math.round(combinedCF)) : estMonthlyRent === null ? "No comp data" : "Enter pmt",
            highlight: combinedCF !== null && combinedCF > 0,
            subtext: combinedCF !== null ? "/month" : undefined,
          },
          {
            label: "Total Equity",
            value: totalEquity > 0 ? fmt(totalEquity) : "N/A",
            highlight: totalEquity > 0,
          },
          {
            label: "Exit Paths",
            value: exitPaths.length > 0 ? exitPaths.length.toString() : "N/A",
            subtext: exitPaths.length > 0 ? exitPaths.join(", ") : undefined,
          },
        ]}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------

export default function DealHeroCard({ report, dealType }: DealHeroCardProps) {
  const DEAL_LABELS: Record<DealType, string> = {
    land_deal: "Land Deal Analysis",
    wholesale: "Wholesale Analysis",
    creative_finance: "Creative Finance Analysis",
    hybrid: "Hybrid Analysis",
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-[11px] font-semibold uppercase tracking-wider text-amber-700 dark:bg-amber-950/50 dark:text-amber-400">
          {DEAL_LABELS[dealType]}
        </span>
      </div>
      {dealType === "land_deal" && <LandDealHero report={report} />}
      {dealType === "wholesale" && <WholesaleHero report={report} />}
      {dealType === "creative_finance" && <CreativeFinanceHero report={report} />}
      {dealType === "hybrid" && <HybridHero report={report} />}
    </div>
  );
}
