"use client";

import { useState, useEffect } from "react";

interface Lead {
  owner_name: string;
  property_address: string;
  county: string;
  lot_acres: number;
  max_units: number;
  estimated_offer: number;
  deal_score: number;
  status: string;
  owner_phones: string[];
  parcel_id: string;
}

interface PipelineData {
  total_leads: number;
  by_status: Record<string, number>;
  top_deals: Lead[];
  hidden_gems_count: number;
  due_follow_up: number;
  avg_score: number;
  counties: Record<string, number>;
}

const STEPS = [
  { icon: "🔍", label: "Research", desc: "Verify info, zoning" },
  { icon: "📞", label: "Contact", desc: "Initial outreach" },
  { icon: "📋", label: "Script", desc: "Sales questions" },
  { icon: "🏗️", label: "Evaluate", desc: "Zoning + env" },
  { icon: "💰", label: "Offer", desc: "Comps + price" },
  { icon: "📄", label: "Documents", desc: "LOI + contract" },
  { icon: "✅", label: "Close", desc: "Permits + done" },
];

const STATUS_COLORS: Record<string, string> = {
  new: "bg-gray-200",
  contacted: "bg-blue-200",
  interested: "bg-yellow-200",
  evaluating: "bg-purple-200",
  offer_made: "bg-orange-200",
  contract_sent: "bg-green-200",
  closed: "bg-emerald-300",
  dead: "bg-red-200",
};

export default function PipelinePage() {
  const [data, setData] = useState<PipelineData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/api/v1/pipeline/snapshot")
      .then((r) => r.json())
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-8 text-gray-500">Loading pipeline...</div>;
  if (!data) return <div className="p-8 text-gray-500">Pipeline API not connected. Run the backend.</div>;

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">🏗️ Land Acquisition Pipeline</h1>
        <span className="text-sm text-gray-500">{data.total_leads} leads</span>
      </div>

      {/* Stats Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <StatCard label="Total Leads" value={data.total_leads} color="blue" />
        <StatCard label="Hidden Gems" value={data.hidden_gems_count} color="purple" />
        <StatCard label="Due Follow-up" value={data.due_follow_up} color="orange" />
        <StatCard label="Avg Score" value={`${data.avg_score}/10`} color="green" />
      </div>

      {/* Pipeline Flow */}
      <div className="bg-white rounded-lg border p-4">
        <h2 className="font-semibold mb-3">Pipeline Flow</h2>
        <div className="flex items-center gap-1 overflow-x-auto">
          {STEPS.map((step, i) => (
            <div key={step.label} className="flex items-center gap-1">
              <div className="flex flex-col items-center px-3 py-2 rounded-lg border bg-gray-50 min-w-[80px]">
                <span className="text-xl">{step.icon}</span>
                <span className="text-xs font-medium">{step.label}</span>
                <span className="text-[10px] text-gray-400">{step.desc}</span>
              </div>
              {i < STEPS.length - 1 && <span className="text-gray-300">→</span>}
            </div>
          ))}
        </div>
      </div>

      {/* Top Deals */}
      <div className="bg-white rounded-lg border p-4">
        <h2 className="font-semibold mb-3">🔥 Top Deals</h2>
        <div className="space-y-2">
          {data.top_deals?.slice(0, 5).map((deal, i) => (
            <div key={i} className="flex items-center justify-between p-3 bg-gray-50 rounded border">
              <div>
                <span className="font-medium">{deal.owner_name}</span>
                <span className="text-sm text-gray-500 ml-2">{deal.property_address || "N/A"}</span>
              </div>
              <div className="flex items-center gap-3 text-sm">
                <span>{deal.county}</span>
                <span>{deal.lot_acres?.toFixed(1)}ac</span>
                <span className="font-medium">{deal.max_units}u</span>
                <span className="text-green-700 font-semibold">${deal.estimated_offer?.toLocaleString()}</span>
                <span className={`px-2 py-0.5 rounded text-xs font-bold ${deal.deal_score >= 7 ? "bg-green-100 text-green-800" : deal.deal_score >= 4 ? "bg-yellow-100 text-yellow-800" : "bg-gray-100 text-gray-600"}`}>
                  {deal.deal_score}/10
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Hidden Gems + Counties */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-white rounded-lg border p-4">
          <h2 className="font-semibold mb-3">📍 By County</h2>
          <div className="space-y-2">
            {Object.entries(data.counties || {}).map(([county, count]) => (
              <div key={county} className="flex justify-between text-sm">
                <span>{county}</span>
                <span className="font-medium">{count}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="bg-white rounded-lg border p-4">
          <h2 className="font-semibold mb-3">📊 Status Breakdown</h2>
          <div className="space-y-1">
            {Object.entries(data.by_status || {}).map(([status, count]) => (
              <div key={status} className="flex justify-between text-sm">
                <span>{status.replace(/_/g, " ")}</span>
                <span className="font-medium">{count}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: string | number; color: string }) {
  const colors: Record<string, string> = {
    blue: "border-blue-200 bg-blue-50",
    purple: "border-purple-200 bg-purple-50",
    orange: "border-orange-200 bg-orange-50",
    green: "border-green-200 bg-green-50",
  };
  return (
    <div className={`rounded-lg border p-4 ${colors[color] || colors.blue}`}>
      <div className="text-xs text-gray-500 uppercase">{label}</div>
      <div className="text-2xl font-bold">{value}</div>
    </div>
  );
}
