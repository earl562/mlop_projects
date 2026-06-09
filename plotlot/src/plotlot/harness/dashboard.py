"""Visual pipeline dashboard — CLI-based view of all acquisition steps.

Shows each lead's progress through the 7-step workflow visually.
Updates in real-time as pipeline advances.
"""

from __future__ import annotations

from typing import Any

from plotlot.harness.lead_management import LeadPipeline, VacantLandLead, LeadStatus

PIPELINE_STEPS = [
    ("🔍", "RESEARCH", "Verify info, zoning, acreage"),
    ("📞", "CONTACT", "Initial outreach via SMS/call"),
    ("📋", "SCRIPT", "Sales script questions"),
    ("🏗️", "EVALUATE", "Zoning, environmental, FAR"),
    ("💰", "OFFER", "Comps + offer calculation"),
    ("📄", "DOCUMENTS", "LOI + contract generation"),
    ("✅", "CLOSE", "Permits + calendar + close"),
]

STATUS_ICONS = {
    "new": "⚪",
    "researching": "🔍",
    "contact_1": "📞",
    "contact_2": "📞",
    "contact_3": "📞",
    "contacted": "📱",
    "interested": "⭐",
    "not_interested": "❌",
    "evaluating": "🏗️",
    "offer_made": "💰",
    "negotiating": "🤝",
    "contract_sent": "📄",
    "contract_signed": "✍️",
    "closed": "✅",
    "dead": "💀",
}


class VisualPipeline:
    """CLI dashboard for the land acquisition pipeline."""

    def __init__(self, pipeline: LeadPipeline):
        self._pipeline = pipeline

    def render(self) -> str:
        """Render the full pipeline dashboard."""
        stats = self._pipeline.stats()
        tops = self._pipeline.top_deals(min_score=4, limit=8)
        gems = self._pipeline.hidden_gems()[:3]
        due = self._pipeline.due_for_follow_up()[:3]

        lines = ["╔" + "═" * 68 + "╗"]
        lines.append("║" + "  🏗️  PLOTLOT — LAND ACQUISITION DASHBOARD".ljust(68) + "║")
        lines.append("╠" + "═" * 68 + "╣")

        # Pipeline flow
        flow = " → ".join(f"{STATUS_ICONS.get(s, '⚪')} {s.replace('_',' ')}" for s in ["new","contacted","interested","evaluating","offer_made","contract_sent","closed"])
        lines.append("║  FLOW: " + flow[:63].ljust(63) + "║")
        lines.append("╠" + "═" * 68 + "╣")

        # Stats row
        total = stats["total_leads"]
        by_status = stats.get("by_status", {})
        interested = by_status.get("interested", 0)
        offers = by_status.get("offer_made", 0)
        closed = by_status.get("closed", 0)
        dead = by_status.get("dead", 0)
        lines.append(f"║  📊 {total} leads | ⭐ {interested} interested | 💰 {offers} offers | ✅ {closed} closed | 💀 {dead} dead".ljust(71) + "║")
        lines.append("╠" + "═" * 68 + "╣")

        # Top deals
        lines.append("║  🔥 TOP DEALS:".ljust(71) + "║")
        for i, l in enumerate(tops, 1):
            icon = STATUS_ICONS.get(l.status.value, "⚪")
            addr = (l.property_address or l.apn)[:20]
            lines.append(f"║  {i}. {icon} {l.owner_name[:18]:18s} | {addr:20s} | {l.lot_acres:4.1f}ac | {l.max_units}u | ${l.estimated_offer:,.0f} | {l.deal_score}/10".ljust(70) + "║")

        lines.append("╠" + "═" * 68 + "╣")

        # Hidden gems
        if gems:
            lines.append("║  💎 HIDDEN GEMS:".ljust(71) + "║")
            for i, l in enumerate(gems, 1):
                lines.append(f"║  {i}. {l.owner_name[:25]:25s} | {l.lot_acres:5.1f}ac | {l.max_units}u | {l.county}".ljust(70) + "║")

        # Follow-ups
        if due:
            lines.append("╠" + "═" * 68 + "╣")
            lines.append("║  ⏰ FOLLOW-UPS DUE:".ljust(71) + "║")
            for i, l in enumerate(due, 1):
                lines.append(f"║  {i}. {l.owner_name[:25]:25s} | Due: {l.next_follow_up} | {l.contact_attempts} attempts".ljust(70) + "║")

        # Step progress bar
        lines.append("╠" + "═" * 68 + "╣")
        lines.append("║  PIPELINE PROGRESS:".ljust(71) + "║")
        for icon, step, desc in PIPELINE_STEPS:
            count = self._count_at_step(step)
            bar = "█" * min(count, 30)
            lines.append(f"║  {icon} {step:12s} | {bar}{' ' + str(count) if count > 0 else ''}".ljust(70) + "║")

        lines.append("╚" + "═" * 68 + "╝")
        return "\n".join(lines)

    def _count_at_step(self, step: str) -> int:
        mapping = {"RESEARCH": "researching", "CONTACT": "contacted", "SCRIPT": "interested", "EVALUATE": "evaluating", "OFFER": "offer_made", "DOCUMENTS": "contract_sent", "CLOSE": "closed"}
        status_val = mapping.get(step, "")
        if status_val:
            try:
                return self._pipeline.stats()["by_status"].get(status_val, 0)
            except Exception:
                pass
        return 0

    def lead_detail(self, lead: VacantLandLead) -> str:
        """Render a single lead's detail view with all 7 steps."""
        z_icon = "✅" if lead.zoning_compliant else ("⚠️" if lead.zoning_compliant is not None else "⚪")
        u_icon = "✅" if lead.utilities_available else ("⚠️" if lead.utilities_available is not None else "⚪")
        e_icon = "✅" if not lead.environmental_flags else f"⚠️ {len(lead.environmental_flags)} flags"

        lines = [f"╔{'═'*58}╗"]
        lines.append(f"║  {lead.owner_name[:40]:40s} {'⭐' if lead.max_units >= 2 else '  '}  ║")
        lines.append(f"║  {lead.property_address or lead.apn}, {lead.property_city} {lead.property_state}".ljust(61) + "║")
        lines.append(f"╠{'═'*58}╣")
        lines.append(f"║  🔍 RESEARCH:  {lead.lot_acres:.1f}ac | {lead.county} | APN:{lead.apn}".ljust(61) + "║")
        lines.append(f"║  📞 CONTACT:   {lead.contact_attempts} attempts | {lead.owner_phones[:2] if lead.owner_phones else ['no phone']}".ljust(61) + "║")
        lines.append(f"║  📋 SCRIPT:    Status: {lead.status.value}".ljust(61) + "║")
        lines.append(f"║  🏗️ EVALUATE:  Zone:{z_icon} | Util:{u_icon} | Env:{e_icon} | Max:{lead.max_units}u".ljust(61) + "║")
        lines.append(f"║  💰 OFFER:     ${lead.estimated_offer:,.0f} | Score:{lead.deal_score}/10".ljust(61) + "║")
        lines.append(f"║  📄 DOCUMENTS: {'Ready' if lead.status.value in ('offer_made','contract_sent','contract_signed','closed') else 'Pending'}".ljust(61) + "║")
        lines.append(f"║  ✅ CLOSE:     {'Closed' if lead.status == LeadStatus.CLOSED else 'Next: ' + lead.next_follow_up or 'Pending'}".ljust(61) + "║")
        lines.append(f"╚{'═'*58}╝")
        return "\n".join(lines)
