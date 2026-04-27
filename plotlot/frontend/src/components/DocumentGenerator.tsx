"use client";

import { useState } from "react";
import {
  generateDocument,
  previewDocument,
  type DocumentPreviewData,
  type ZoningReportData,
} from "@/lib/api";

interface DocumentGeneratorProps {
  report: ZoningReportData;
}

const DOCUMENT_TYPES = [
  { value: "loi", label: "Letter of Intent (LOI)", format: "docx" },
  { value: "deal_summary", label: "Deal Summary Report", format: "docx" },
  { value: "psa", label: "Purchase & Sale Agreement", format: "docx" },
  { value: "proforma_spreadsheet", label: "Pro Forma Spreadsheet", format: "xlsx" },
] as const;

const DEAL_TYPES = [
  { value: "land_deal", label: "Land Deal" },
  { value: "wholesale", label: "Wholesale" },
  { value: "seller_finance", label: "Seller Finance" },
  { value: "creative_finance", label: "Creative Finance" },
  { value: "subject_to", label: "Subject To" },
  { value: "wrap", label: "Wrap" },
  { value: "hybrid", label: "Hybrid" },
] as const;

function DealContextStrip({ dealType, report }: { dealType: string; report: ZoningReportData }) {
  const chips: Array<{ label: string; value: string }> = [];

  if (dealType === "land_deal") {
    const maxUnits = report.density_analysis?.max_units;
    const maxOffer = report.pro_forma?.max_land_price;
    const governing = report.density_analysis?.governing_constraint?.replace(/_/g, " ");
    if (maxUnits != null) chips.push({ label: "Max Units", value: maxUnits.toString() });
    if (maxOffer) chips.push({ label: "Max Offer (RLV)", value: `$${maxOffer.toLocaleString(undefined, { maximumFractionDigits: 0 })}` });
    if (governing) chips.push({ label: "Governing", value: governing });
  } else if (dealType === "wholesale") {
    const arv = report.comp_analysis?.adv_per_unit ?? report.comp_analysis?.estimated_land_value;
    const mao = arv ? arv * 0.7 : null;
    const repairEst = arv ? arv * 0.1 : null;
    if (arv) chips.push({ label: "ARV", value: `$${arv.toLocaleString(undefined, { maximumFractionDigits: 0 })}` });
    if (mao) chips.push({ label: "MAO (70%)", value: `$${mao.toLocaleString(undefined, { maximumFractionDigits: 0 })}` });
    if (repairEst) chips.push({ label: "Repair Est.", value: `$${repairEst.toLocaleString(undefined, { maximumFractionDigits: 0 })}` });
  } else if (dealType === "seller_finance" || dealType === "creative_finance") {
    const mv = report.property_record?.market_value;
    const arv = report.comp_analysis?.adv_per_unit ?? report.comp_analysis?.estimated_land_value;
    const equity = mv && arv ? arv - mv : null;
    if (mv) chips.push({ label: "Market Value", value: `$${mv.toLocaleString(undefined, { maximumFractionDigits: 0 })}` });
    if (equity && equity > 0) chips.push({ label: "Equity Est.", value: `$${equity.toLocaleString(undefined, { maximumFractionDigits: 0 })}` });
  }

  if (chips.length === 0) return null;

  return (
    <div className="mb-4 flex flex-wrap gap-2">
      {chips.map(({ label, value }) => (
        <div key={label} className="rounded-lg bg-amber-50 px-3 py-1.5 dark:bg-amber-950/30">
          <span className="text-[10px] font-medium uppercase tracking-wider text-amber-600 dark:text-amber-500">{label}</span>
          <div className="text-sm font-bold text-amber-800 dark:text-amber-300">{value}</div>
        </div>
      ))}
    </div>
  );
}

function buildContextFromReport(report: ZoningReportData): Record<string, string | number> {
  const ctx: Record<string, string | number> = {};

  // Property
  if (report.address) ctx.property_address = report.address;
  if (report.formatted_address) ctx.formatted_address = report.formatted_address;
  if (report.municipality) ctx.municipality = report.municipality;
  if (report.county) ctx.county = report.county;

  // Zoning
  if (report.zoning_district) ctx.zoning_district = report.zoning_district;
  if (report.zoning_description) ctx.zoning_description = report.zoning_description;
  if (report.max_height) ctx.max_height = report.max_height;
  if (report.max_density) ctx.max_density = report.max_density;

  // Property record
  if (report.property_record) {
    const pr = report.property_record;
    if (pr.folio) ctx.apn = pr.folio;
    if (pr.lot_size_sqft) ctx.lot_size_sqft = pr.lot_size_sqft;
    if (pr.year_built) ctx.year_built = pr.year_built;
    if (pr.owner) ctx.owner = pr.owner;
  }

  // Density
  if (report.density_analysis) {
    ctx.max_units = report.density_analysis.max_units;
    ctx.governing_constraint = report.density_analysis.governing_constraint;
  }

  // Comps
  if (report.comp_analysis) {
    ctx.median_price_per_acre = report.comp_analysis.median_price_per_acre;
    ctx.estimated_land_value = report.comp_analysis.estimated_land_value;
    ctx.comp_count = report.comp_analysis.comparables.length;
  }

  // Pro forma
  if (report.pro_forma) {
    ctx.gross_development_value = report.pro_forma.gross_development_value;
    ctx.hard_costs = report.pro_forma.hard_costs;
    ctx.soft_costs = report.pro_forma.soft_costs;
    ctx.builder_margin = report.pro_forma.builder_margin;
    ctx.max_land_price = report.pro_forma.max_land_price;
    ctx.cost_per_door = report.pro_forma.cost_per_door;
    ctx.adv_per_unit = report.pro_forma.adv_per_unit;
  }

  // AI
  if (report.summary) ctx.summary = report.summary;
  if (report.confidence) ctx.confidence = report.confidence;

  return ctx;
}

export default function DocumentGenerator({ report }: DocumentGeneratorProps) {
  const [documentType, setDocumentType] = useState("deal_summary");
  const [dealType, setDealType] = useState("land_deal");
  const [generating, setGenerating] = useState(false);
  const [previewing, setPreviewing] = useState(false);
  const [preview, setPreview] = useState<DocumentPreviewData | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Additional context fields for LOI/PSA
  const [buyerName, setBuyerName] = useState("");
  const [sellerName, setSellerName] = useState("");
  const [purchasePrice, setPurchasePrice] = useState("");

  const selectedDocType = DOCUMENT_TYPES.find((d) => d.value === documentType);
  const needsPartyInfo = documentType === "psa" || documentType === "loi";

  async function handleGenerate() {
    setGenerating(true);
    setError(null);
    try {
      const ctx = buildContextFromReport(report);
      if (buyerName) ctx.buyer_name = buyerName;
      if (sellerName) ctx.seller_name = sellerName;
      if (purchasePrice) ctx.purchase_price = parseFloat(purchasePrice);

      const blob = await generateDocument({
        document_type: documentType,
        deal_type: dealType,
        context: ctx,
        output_format: selectedDocType?.format,
      });

      // Trigger download
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      const ext = selectedDocType?.format || "docx";
      const addr = (report.address || "property").split(",")[0].replace(/\s+/g, "_").slice(0, 30);
      a.download = `${documentType.toUpperCase()}_${addr}.${ext}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generation failed");
    } finally {
      setGenerating(false);
    }
  }

  async function handlePreview() {
    setPreviewing(true);
    setError(null);
    setPreview(null);
    try {
      const ctx = buildContextFromReport(report);
      if (buyerName) ctx.buyer_name = buyerName;
      if (sellerName) ctx.seller_name = sellerName;
      if (purchasePrice) ctx.purchase_price = parseFloat(purchasePrice);

      const data = await previewDocument({
        document_type: documentType,
        deal_type: dealType,
        context: ctx,
      });
      setPreview(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Preview failed");
    } finally {
      setPreviewing(false);
    }
  }

  return (
    <div className="rounded-xl border bg-white p-6 shadow-sm dark:border-stone-700 dark:bg-stone-900">
      <h3 className="mb-4 text-lg font-semibold text-stone-900 dark:text-stone-100">
        Generate Documents
      </h3>

      <DealContextStrip dealType={dealType} report={report} />

      <div className="grid gap-4 sm:grid-cols-2">
        {/* Document type */}
        <div>
          <label className="mb-1 block text-sm font-medium text-stone-700 dark:text-stone-300">
            Document Type
          </label>
          <select
            value={documentType}
            onChange={(e) => {
              setDocumentType(e.target.value);
              setPreview(null);
            }}
            className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm dark:border-stone-600 dark:bg-stone-800 dark:text-stone-100"
          >
            {DOCUMENT_TYPES.map((dt) => (
              <option key={dt.value} value={dt.value}>
                {dt.label}
              </option>
            ))}
          </select>
        </div>

        {/* Deal type */}
        <div>
          <label className="mb-1 block text-sm font-medium text-stone-700 dark:text-stone-300">
            Deal Type
          </label>
          <select
            value={dealType}
            onChange={(e) => {
              setDealType(e.target.value);
              setPreview(null);
            }}
            className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm dark:border-stone-600 dark:bg-stone-800 dark:text-stone-100"
          >
            {DEAL_TYPES.map((dt) => (
              <option key={dt.value} value={dt.value}>
                {dt.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Party info (LOI/PSA) */}
      {needsPartyInfo && (
        <div className="mt-4 grid gap-4 sm:grid-cols-3">
          <div>
            <label className="mb-1 block text-sm font-medium text-stone-700 dark:text-stone-300">
              Buyer Name
            </label>
            <input
              type="text"
              value={buyerName}
              onChange={(e) => setBuyerName(e.target.value)}
              placeholder="EP Ventures LLC"
              className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm dark:border-stone-600 dark:bg-stone-800 dark:text-stone-100"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-stone-700 dark:text-stone-300">
              Seller Name
            </label>
            <input
              type="text"
              value={sellerName}
              onChange={(e) => setSellerName(e.target.value)}
              placeholder="Property Owner"
              className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm dark:border-stone-600 dark:bg-stone-800 dark:text-stone-100"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-stone-700 dark:text-stone-300">
              Purchase Price
            </label>
            <input
              type="number"
              value={purchasePrice}
              onChange={(e) => setPurchasePrice(e.target.value)}
              placeholder="350000"
              className="w-full rounded-lg border border-stone-300 bg-white px-3 py-2 text-sm dark:border-stone-600 dark:bg-stone-800 dark:text-stone-100"
            />
          </div>
        </div>
      )}

      {/* Actions */}
      <div className="mt-4 flex gap-3">
        <button
          onClick={handlePreview}
          disabled={previewing}
          className="rounded-lg border border-amber-600 px-4 py-2 text-sm font-medium text-amber-700 transition-colors hover:bg-amber-50 disabled:opacity-50 dark:border-amber-500 dark:text-amber-400 dark:hover:bg-amber-900/20"
        >
          {previewing ? "Loading..." : "Preview"}
        </button>
        <button
          onClick={handleGenerate}
          disabled={generating}
          className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-amber-700 disabled:opacity-50"
        >
          {generating
            ? "Generating..."
            : `Download .${selectedDocType?.format || "docx"}`}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div className="mt-3 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-400">
          {error}
        </div>
      )}

      {/* Preview skeleton */}
      {previewing && (
        <div className="mt-4 space-y-3 rounded-lg border border-[var(--border)] bg-[var(--bg-surface-raised)] p-4">
          <div className="flex items-center justify-between">
            <div className="h-3 w-28 animate-shimmer rounded" />
            <div className="h-3 w-12 animate-shimmer rounded" />
          </div>
          {[1, 2, 3].map((i) => (
            <div key={i} className="space-y-2 border-b border-[var(--border)] pb-3">
              <div className="h-3.5 w-1/3 animate-shimmer rounded" />
              <div className="h-3 w-full animate-shimmer rounded" />
              <div className="h-3 w-5/6 animate-shimmer rounded" />
              <div className="h-3 w-4/6 animate-shimmer rounded" />
            </div>
          ))}
        </div>
      )}

      {/* Preview */}
      {!previewing && preview && (
        <div className="mt-4 rounded-lg border border-stone-200 bg-stone-50 p-4 dark:border-stone-700 dark:bg-stone-800/50">
          <div className="mb-3 flex items-center justify-between">
            <span className="text-sm font-medium text-stone-700 dark:text-stone-300">
              Preview: {preview.clause_count} clauses
            </span>
            <button
              onClick={() => setPreview(null)}
              className="text-xs text-stone-500 hover:text-stone-700 dark:text-stone-400"
            >
              Close
            </button>
          </div>
          <div className="max-h-96 space-y-3 overflow-y-auto">
            {preview.clauses.map((clause) => (
              <div key={clause.id} className="border-b border-stone-200 pb-3 dark:border-stone-700">
                <h4 className="text-sm font-semibold text-stone-800 dark:text-stone-200">
                  {clause.title}
                </h4>
                <pre className="mt-1 whitespace-pre-wrap text-xs text-stone-600 dark:text-stone-400">
                  {clause.content.slice(0, 500)}
                  {clause.content.length > 500 ? "..." : ""}
                </pre>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
