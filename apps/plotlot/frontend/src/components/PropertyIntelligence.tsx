"use client";

import { ZoningReportData } from "@/lib/api";

interface PropertyIntelligenceProps {
  report: ZoningReportData;
}

interface Flag {
  severity: "critical" | "warning" | "positive";
  text: string;
}

function SeverityDot({ severity }: { severity: Flag["severity"] }) {
  const colors: Record<string, string> = {
    critical: "bg-red-500",
    warning: "bg-amber-500",
    positive: "bg-emerald-500",
  };
  return <div className={`mt-1 h-2 w-2 shrink-0 rounded-full ${colors[severity]}`} />;
}

export default function PropertyIntelligence({ report }: PropertyIntelligenceProps) {
  const lotSize = report.density_analysis?.lot_size_sqft || report.property_record?.lot_size_sqft || 0;
  const buildingArea = report.property_record?.building_area_sqft || 0;
  const far = report.numeric_params?.far || null;
  const lotCoveragePct = report.numeric_params?.max_lot_coverage_pct || null;
  const minLotSize = report.numeric_params?.min_lot_area_per_unit_sqft || 0;
  const lotWidth = report.density_analysis?.lot_width_ft || report.numeric_params?.min_lot_width_ft || 0;
  const lotDepth = report.density_analysis?.lot_depth_ft || 0;
  const setbackFront = report.numeric_params?.setback_front_ft || 0;
  const setbackSide = report.numeric_params?.setback_side_ft || 0;
  const setbackRear = report.numeric_params?.setback_rear_ft || 0;

  // --- Utilization Analysis ---
  let maxBuildable = 0;
  let utilizationLabel = "";
  if (far && far > 0 && lotSize > 0) {
    maxBuildable = far * lotSize;
    utilizationLabel = `FAR ${far} x ${lotSize.toLocaleString()} sqft`;
  } else if (lotCoveragePct && lotCoveragePct > 0 && lotSize > 0) {
    maxBuildable = (lotCoveragePct / 100) * lotSize;
    utilizationLabel = `${lotCoveragePct}% coverage x ${lotSize.toLocaleString()} sqft`;
  }
  const currentPct = maxBuildable > 0 && buildingArea > 0 ? (buildingArea / maxBuildable) * 100 : 0;
  const upside = maxBuildable > 0 && buildingArea > 0 ? maxBuildable - buildingArea : 0;
  const showUtilization = maxBuildable > 0 && buildingArea > 0;

  // --- Lot Analysis ---
  const excessPct = minLotSize > 0 && lotSize > 0 ? ((lotSize - minLotSize) / minLotSize) * 100 : 0;
  const subdivisible = minLotSize > 0 && lotSize >= 2 * minLotSize;
  const subdivisibleLots = minLotSize > 0 ? Math.floor(lotSize / minLotSize) : 0;
  const buildableFootprint = lotWidth > 0 && lotDepth > 0
    ? Math.max(0, lotWidth - 2 * setbackSide) * Math.max(0, lotDepth - setbackFront - setbackRear)
    : 0;
  const maxStories = report.numeric_params?.max_stories || null;
  const showLotAnalysis = lotSize > 0 && minLotSize > 0;

  // --- Risk Flags ---
  const flags: Flag[] = [];

  // Non-conforming check
  if (report.property_record?.zoning_code && report.zoning_district) {
    const prZoning = report.property_record.zoning_code.trim().toLowerCase();
    const reportZoning = report.zoning_district.trim().toLowerCase();
    if (prZoning && reportZoning && prZoning !== reportZoning) {
      flags.push({
        severity: "critical",
        text: `Zoning mismatch: county records show "${report.property_record.zoning_code}" but analysis found "${report.zoning_district}"`,
      });
    }
  }

  if (!report.property_record) {
    flags.push({ severity: "critical", text: "No property record found — verify address with county property appraiser" });
  }

  if (report.confidence === "low") {
    flags.push({ severity: "warning", text: "Low confidence data — obtain zoning verification letter from municipality" });
  }

  if (report.property_record?.year_built && report.property_record.year_built > 0 && report.property_record.year_built < 1970) {
    flags.push({ severity: "warning", text: `Structure built in ${report.property_record.year_built} — predates modern zoning codes` });
  }

  if (report.property_record?.owner) {
    const owner = report.property_record.owner.toUpperCase();
    const isCorporate = /\b(LLC|CORP|INC|TRUST|LP|LLP|PARTNERSHIP)\b/.test(owner);
    const isResidential = /^R/i.test(report.zoning_district);
    if (isCorporate && isResidential) {
      flags.push({ severity: "warning", text: "Corporate owner on residential lot — review entity structure for assignment feasibility" });
    }
  }

  if (report.property_record && report.property_record.building_area_sqft === 0) {
    flags.push({ severity: "warning", text: "No building area recorded — may be vacant lot" });
  }

  // Positive flags
  if (report.property_record?.zoning_code && report.zoning_district) {
    const prZoning = report.property_record.zoning_code.trim().toLowerCase();
    const reportZoning = report.zoning_district.trim().toLowerCase();
    if (prZoning === reportZoning) {
      flags.push({ severity: "positive", text: "Conforming use — zoning codes match across data sources" });
    }
  }

  if (excessPct > 10) {
    flags.push({ severity: "positive", text: `Lot exceeds minimum size by ${Math.round(excessPct)}%` });
  }

  if (currentPct > 0 && currentPct < 80) {
    flags.push({ severity: "positive", text: `Only ${Math.round(currentPct)}% of maximum buildable area utilized` });
  }

  // --- Smart Next Steps ---
  const county = report.county || "county";
  const municipality = report.municipality || "municipality";
  const hasZoningMismatch = flags.some((f) => f.text.includes("Zoning mismatch"));
  const hasCorporateOwner = flags.some((f) => f.text.includes("Corporate owner"));
  const hasPreModern = flags.some((f) => f.text.includes("predates"));

  const nextSteps = [
    { text: `Pull title search${report.property_record?.folio ? ` (Folio: ${report.property_record.folio})` : ""}`, show: true },
    { text: "Check FEMA flood zone designation", show: true },
    { text: `Verify zoning with ${municipality} planning department`, show: report.confidence !== "high" },
    { text: `Review non-conforming status with ${county} County DERM/RER`, show: hasZoningMismatch },
    { text: "Review abandonment rule — 180+ days vacancy = loss of non-conforming rights", show: hasZoningMismatch },
    { text: `Obtain zoning verification letter from ${municipality}`, show: report.confidence === "low" },
    { text: "Review corporate structure for assignment feasibility", show: hasCorporateOwner },
    { text: "Order property condition assessment (pre-1970 structure)", show: hasPreModern },
    { text: `Investigate subdivision potential with ${county} County planning dept`, show: subdivisible },
    { text: `Verify address with ${county} County property appraiser`, show: !report.property_record },
  ].filter((s) => s.show);

  return (
    <div className="space-y-4">
      {/* Utilization Analysis */}
      {showUtilization && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Utilization Analysis</h4>
          <div className="rounded-lg bg-stone-50 dark:bg-stone-800/50 p-3 space-y-2">
            <div className="flex justify-between text-xs">
              <span className="text-stone-600">Current: {buildingArea.toLocaleString()} sqft built</span>
              <span className="font-medium text-stone-700">{Math.round(currentPct)}% utilized</span>
            </div>
            {/* Progress bar */}
            <div className="h-2 w-full rounded-full bg-stone-200 dark:bg-stone-700">
              <div
                className="h-2 rounded-full bg-amber-500 transition-all"
                style={{ width: `${Math.min(currentPct, 100)}%` }}
              />
            </div>
            <div className="flex justify-between text-xs text-stone-500">
              <span>Maximum: {Math.round(maxBuildable).toLocaleString()} sqft ({utilizationLabel})</span>
            </div>
            {upside > 0 && (
              <div className="text-xs font-medium text-emerald-700 dark:text-emerald-400">
                +{Math.round(upside).toLocaleString()} sqft additional development capacity
              </div>
            )}
          </div>
        </div>
      )}

      {/* Lot Analysis */}
      {showLotAnalysis && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Lot Analysis</h4>
          <div className="rounded-lg bg-stone-50 dark:bg-stone-800/50 p-3 space-y-1.5 text-xs text-stone-600 dark:text-stone-400">
            {excessPct > 0 ? (
              <p>Lot exceeds minimum by {Math.round(excessPct)}% ({lotSize.toLocaleString()} vs {minLotSize.toLocaleString()} sqft required)</p>
            ) : (
              <p>Lot meets minimum size requirement ({lotSize.toLocaleString()} sqft, {minLotSize.toLocaleString()} sqft required)</p>
            )}
            {subdivisible ? (
              <p className="font-medium text-amber-700 dark:text-amber-400">
                Potential subdivision into {subdivisibleLots} conforming lots (would need {(subdivisibleLots * minLotSize).toLocaleString()} sqft)
              </p>
            ) : minLotSize > 0 ? (
              <p>Not subdivisible (would need {(2 * minLotSize).toLocaleString()} sqft for 2 conforming lots)</p>
            ) : null}
            {buildableFootprint > 0 && (
              <p>
                Buildable envelope: {Math.round(buildableFootprint).toLocaleString()} sqft footprint
                {maxStories ? ` x ${maxStories} stories` : ""}
              </p>
            )}
          </div>
        </div>
      )}

      {/* Risk Flags */}
      {flags.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Risk Flags</h4>
          <div className="space-y-1.5">
            {flags.map((flag, i) => (
              <div key={i} className="flex items-start gap-2 text-xs text-stone-600 dark:text-stone-400">
                <SeverityDot severity={flag.severity} />
                <span>{flag.text}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Smart Next Steps */}
      {nextSteps.length > 0 && (
        <div className="space-y-2">
          <h4 className="text-xs font-semibold text-stone-500 uppercase tracking-wider">Next Steps</h4>
          <div className="space-y-1.5">
            {nextSteps.map((step, i) => (
              <div key={i} className="flex items-start gap-2 text-xs text-stone-600 dark:text-stone-400">
                <div className="mt-0.5 h-3.5 w-3.5 shrink-0 rounded border border-stone-300 dark:border-stone-600" />
                <span>{step.text}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
