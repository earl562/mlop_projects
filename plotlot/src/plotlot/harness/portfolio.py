"""Portfolio dashboard — multi-property pipeline overview.

Summary view across all acquisition stages:
- Pipeline stats (new, contacted, interested, contracted, closed)
- Top deals by score
- Hidden gems
- Upcoming deadlines
- Outreach stats
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from plotlot.harness.lead_management import LeadPipeline, LeadStatus


@dataclass
class PipelineSnapshot:
    total_leads: int = 0
    by_status: dict[str, int] = field(default_factory=dict)
    by_county: dict[str, int] = field(default_factory=dict)
    top_deals: list[dict[str, Any]] = field(default_factory=list)
    hidden_gems_count: int = 0
    due_follow_up: int = 0
    avg_score: float = 0.0
    total_potential_value: float = 0.0


class PortfolioDashboard:
    """Multi-property view across the entire acquisition pipeline."""

    def __init__(self, pipeline: LeadPipeline):
        self._pipeline = pipeline

    def snapshot(self) -> PipelineSnapshot:
        stats = self._pipeline.stats()
        scored = [l for l in self._pipeline._leads.values() if l.deal_score > 0]
        avg = sum(l.deal_score for l in scored) / len(scored) if scored else 0
        total_val = sum(l.estimated_offer for l in scored if l.estimated_offer > 0)
        tops = self._pipeline.top_deals(min_score=5, limit=5)
        return PipelineSnapshot(
            total_leads=stats["total_leads"],
            by_status=stats["by_status"],
            by_county=stats["counties"],
            top_deals=[{"name": l.owner_name, "county": l.county, "acres": round(l.lot_acres, 1), "score": l.deal_score, "offer": l.estimated_offer, "units": l.max_units, "phones": l.owner_phones[:2]} for l in tops],
            hidden_gems_count=stats["hidden_gems"],
            due_follow_up=stats["due_follow_up"],
            avg_score=round(avg, 1),
            total_potential_value=total_val,
        )

    def summary_markdown(self) -> str:
        s = self.snapshot()
        lines = [
            "# PlotLot — Land Acquisition Dashboard",
            "",
            f"**{s.total_leads}** total leads | **{s.hidden_gems_count}** hidden gems | **{s.due_follow_up}** due for follow-up",
            f"Average deal score: **{s.avg_score}/10** | Portfolio potential: **${s.total_potential_value:,.0f}**",
            "",
            "## Pipeline Status",
        ]
        status_order = ["new", "contact_1", "contact_2", "contact_3", "contacted", "interested", "evaluating", "offer_made", "negotiating", "contract_sent", "contract_signed", "closed", "dead"]
        for status in status_order:
            count = s.by_status.get(status, 0)
            bar = "█" * min(count // (s.total_leads // 40 + 1), 40)
            lines.append(f"- {status:20s}: {count:>5d} {bar}")
        lines.append("")
        lines.append("## By County")
        for county, count in sorted(s.by_county.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"- {county}: {count:,} leads")
        lines.append("")
        lines.append("## Top 5 Deals")
        for i, deal in enumerate(s.top_deals, 1):
            lines.append(f"{i}. **{deal['name']}** — {deal['county']}, {deal['acres']}ac, {deal['units']}u, Score:{deal['score']}, ${deal['offer']:,.0f}")
        return "\n".join(lines)

    def quick_stats(self) -> dict[str, Any]:
        s = self.snapshot()
        return {"leads": s.total_leads, "gems": s.hidden_gems_count, "follow_ups": s.due_follow_up, "avg_score": s.avg_score, "counties": s.by_county, "pipeline_progress": s.by_status}
