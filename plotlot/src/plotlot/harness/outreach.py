"""Outreach automation — seller contact via S2S model with follow-up cadence.

Per user's workflow:
1. Initial contact with sales script questions
2. Follow-up at 1 week, 2 weeks (auto-scheduled)
3. After reaching 20-35 people, someone responds
4. If interested → evaluate property → offer → contract
5. If not → mark dead, move to next

Uses OpenRouter model for personalized message generation.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from plotlot.harness.lead_management import VacantLandLead, LeadStatus
from plotlot.harness.deal_evaluator import generate_sales_script, SALES_SCRIPT_QUESTIONS


@dataclass
class OutreachMessage:
    lead_parcel_id: str
    lead_name: str
    message: str
    channel: str = "sms"  # sms, email, voicemail
    phone: str = ""
    status: str = "pending"  # pending, sent, delivered, responded, bounced
    sent_at: str = ""
    response: str = ""

    @classmethod
    def for_lead(cls, lead: VacantLandLead, attempt: int = 1) -> "OutreachMessage":
        phone = lead.owner_phones[0] if lead.owner_phones else ""
        if attempt == 1:
            msg = cls._intro_message(lead)
        elif attempt == 2:
            msg = cls._follow_up_1(lead)
        else:
            msg = cls._follow_up_2(lead)
        return cls(lead_parcel_id=lead.parcel_id, lead_name=lead.owner_name, message=msg, phone=phone)

    @staticmethod
    def _intro_message(lead: VacantLandLead) -> str:
        addr = lead.property_address or f"parcel {lead.apn}"
        return f"Hi {lead.owner_first}, my name is Earl with ESP & ME LLC. I noticed you own vacant land at {addr} in {lead.property_city}. Would you be open to a conversation about selling? No pressure — just exploring opportunities. Let me know if you'd like to discuss. Thanks!"

    @staticmethod
    def _follow_up_1(lead: VacantLandLead) -> str:
        return f"Hi {lead.owner_first}, just following up on my message about your property at {lead.property_address or f'parcel {lead.apn}'}. I'd love to have a quick 5-minute conversation to see if there's a fit. Feel free to call or text me back anytime."

    @staticmethod
    def _follow_up_2(lead: VacantLandLead) -> str:
        return f"Hi {lead.owner_first}, this is my last outreach about your land. If you're ever interested in selling in the future, keep my number handy. I buy land in {lead.county} County. Wishing you the best either way."


class OutreachPipeline:
    """Automated outreach pipeline — sends messages via OpenRouter model."""

    def __init__(self, leads: list[VacantLandLead], model_caller: Any = None):
        self._leads = leads
        self._sent: list[OutreachMessage] = []
        self._responses: dict[str, str] = {}  # lead_id → response
        self._daily_limit = 50
        self._model_caller = model_caller

    def batch_next(self, limit: int = 10) -> list[OutreachMessage]:
        """Get next batch of leads to contact (new leads, sorted by score)."""
        new = sorted(
            [l for l in self._leads if l.status == LeadStatus.NEW and l.owner_phones and l.deal_score >= 3],
            key=lambda l: l.deal_score, reverse=True,
        )
        return [OutreachMessage.for_lead(l, 1) for l in new[:limit]]

    def follow_ups_due(self) -> list[OutreachMessage]:
        """Get leads that need follow-up messages."""
        due = [l for l in self._leads if l.needs_follow_up()]
        messages = []
        for lead in due:
            attempt = min(lead.contact_attempts + 1, 3)
            messages.append(OutreachMessage.for_lead(lead, attempt))
        return messages

    def record_send(self, msg: OutreachMessage) -> None:
        msg.sent_at = datetime.now(timezone.utc).isoformat()
        msg.status = "sent"
        self._sent.append(msg)

    def record_response(self, lead_parcel_id: str, response: str) -> str:
        self._responses[lead_parcel_id] = response
        interested = any(w in response.lower() for w in ("yes", "interested", "call", "talk", "sell", "offer", "price", "how much"))
        return "interested" if interested else "not_interested"

    def stats(self) -> dict[str, Any]:
        total = len(self._sent)
        responded = len(self._responses)
        interested = sum(1 for r in self._responses.values() if any(w in r.lower() for w in ("yes", "interested", "call", "talk", "sell")))
        return {"total_sent": total, "responses": responded, "response_rate": f"{responded/max(total,1)*100:.1f}%", "interested": interested, "follow_ups_due": len(self.follow_ups_due())}

    async def generate_personalized_message(self, lead: VacantLandLead, attempt: int = 1) -> str:
        """Use OpenRouter model to generate a personalized outreach message."""
        if not self._model_caller:
            return OutreachMessage.for_lead(lead, attempt).message
        from plotlot.harness.middleware import AgentState
        prompt = f"""Write a short, professional SMS to {lead.owner_first} {lead.owner_last} about their vacant land at {lead.property_address or lead.apn}, {lead.property_city} {lead.property_state}.
They own {lead.lot_acres:.1f} acres. Assessed value: ${lead.assessed_value:,.0f}.
Attempt #{attempt}. Keep it under 160 characters. Be warm but not pushy.
Include 'ESP & ME LLC' and a call to action."""
        state = AgentState()
        state.add_message("system", "You are a professional real estate outreach assistant. Write concise, warm, non-pushy SMS messages.")
        state.add_message("user", prompt)
        result = await self._model_caller(state, [])
        for m in result.messages:
            if m.get("role") == "assistant":
                return m["content"][:160]
        return OutreachMessage.for_lead(lead, attempt).message


def daily_outreach_plan(leads: list[VacantLandLead], target_contacts: int = 30) -> list[dict[str, Any]]:
    """Generate a daily outreach plan — which leads to contact and when."""
    plan = []
    pipeline = OutreachPipeline(leads)
    new_batch = pipeline.batch_next(target_contacts)
    follow_ups = pipeline.follow_ups_due()
    for msg in new_batch[:target_contacts - len(follow_ups)]:
        plan.append({"priority": "new", "lead": msg.lead_name, "phone": msg.phone, "message": msg.message[:80] + "..."})
    for msg in follow_ups[:target_contacts]:
        plan.append({"priority": "follow_up", "lead": msg.lead_name, "phone": msg.phone, "message": msg.message[:80] + "..."})
    return plan
