"""Voice agent — inbound/outbound call handling for land acquisition.

Handles the full sales script conversation when a seller calls or is called.
Tracks call state, moves through script questions, logs outcomes.
STT/TTS stubs for external service integration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from plotlot.harness.deal_evaluator import SALES_SCRIPT_QUESTIONS, FIRST_HOLD_MESSAGE, SECOND_HOLD_MESSAGE
from plotlot.harness.lead_management import VacantLandLead


@dataclass
class CallSession:
    call_id: str
    lead_id: str = ""
    lead_name: str = ""
    direction: str = "outbound"  # inbound, outbound
    status: str = "ringing"  # ringing, connected, on_hold, completed, failed, voicemail
    transcript: list[dict[str, str]] = field(default_factory=list)
    current_question: int = 0
    current_phase: str = "intro"  # intro, questions, first_hold, follow_up, second_hold, offer, close
    start_time: str = ""
    end_time: str = ""
    outcome: str = ""  # interested, not_interested, wrong_number, voicemail, callback
    notes: list[str] = field(default_factory=list)
    offer_amount: float = 0.0

    def __post_init__(self):
        if not self.start_time:
            self.start_time = datetime.now(timezone.utc).isoformat()

    def add_transcript(self, speaker: str, text: str) -> None:
        self.transcript.append({"speaker": speaker, "text": text, "time": datetime.now(timezone.utc).isoformat()[:19]})


class VoiceAgent:
    """Handles voice calls through the land acquisition sales script."""

    def __init__(self, leads: dict[str, VacantLandLead], model_caller=None):
        self._leads = leads
        self._sessions: dict[str, CallSession] = {}
        self._model = model_caller

    def match_lead_by_phone(self, phone: str) -> VacantLandLead | None:
        clean = phone.replace("-", "").replace(" ", "").replace("(", "").replace(")", "")[-10:]
        for lead in self._leads.values():
            for p in lead.owner_phones:
                if p.replace("-", "").replace(" ", "")[-10:] == clean:
                    return lead
        return None

    def start_outbound(self, lead_id: str) -> CallSession:
        lead = self._leads.get(lead_id)
        cid = f"call-{lead_id}-{datetime.now(timezone.utc).strftime('%H%M%S')}"
        session = CallSession(call_id=cid, lead_id=lead_id, lead_name=lead.owner_name if lead else "", direction="outbound")
        self._sessions[cid] = session
        session.add_transcript("agent", f"Calling {lead.owner_name} at {lead.owner_phones[0] if lead and lead.owner_phones else 'unknown'}")
        return session

    def handle_inbound(self, phone: str) -> dict[str, Any]:
        lead = self.match_lead_by_phone(phone)
        if not lead:
            return {"matched": False, "message": "Caller not in lead database"}
        cid = f"call-{lead.parcel_id}-{datetime.now(timezone.utc).strftime('%H%M%S')}"
        session = CallSession(call_id=cid, lead_id=lead.parcel_id, lead_name=lead.owner_name, direction="inbound")
        self._sessions[cid] = session
        session.add_transcript("caller", "[Inbound call connected]")
        return {"matched": True, "call_id": cid, "lead_id": lead.parcel_id, "lead_name": lead.owner_name, "property": lead.property_address or lead.apn, "lot_acres": lead.lot_acres, "assessed": lead.assessed_value, "score": lead.deal_score}

    def get_next_script(self, session_id: str) -> str:
        session = self._sessions.get(session_id)
        if not session:
            return "Session not found."
        phase = session.current_phase
        if phase == "intro":
            session.current_phase = "questions"
            return f"Hi, this is Earl with ESP & ME LLC. I'm calling about the property at {self._get_lead(session).property_address or self._get_lead(session).apn}. Is this a good time to talk?"
        elif phase == "questions" and session.current_question < 4:
            q = SALES_SCRIPT_QUESTIONS[session.current_question]
            session.current_question += 1
            return q
        elif phase == "questions" and session.current_question >= 4:
            session.current_phase = "first_hold"
            return FIRST_HOLD_MESSAGE
        elif phase == "first_hold":
            session.current_phase = "follow_up"
            session.current_question = 4
            return "Thanks for holding. I have a few more questions."
        elif phase == "follow_up" and session.current_question < 8:
            q = SALES_SCRIPT_QUESTIONS[session.current_question]
            session.current_question += 1
            return q
        elif phase == "follow_up" and session.current_question >= 8:
            session.current_phase = "second_hold"
            return SECOND_HOLD_MESSAGE
        elif phase == "second_hold":
            session.current_phase = "close"
            lead = self._get_lead(session)
            return f"Our offer for your property is ${session.offer_amount:,.0f}. {self._negotiation_tip(lead)}"
        elif phase == "close":
            session.status = "completed"
            session.end_time = datetime.now(timezone.utc).isoformat()
            return "Thank you for your time. We'll follow up with the paperwork. Have a great day!"
        return "Thank you for the conversation."

    def process_response(self, session_id: str, response: str) -> str:
        session = self._sessions.get(session_id)
        if not session:
            return "Session not found."
        session.add_transcript("caller", response)
        interested_words = ("yes", "interested", "sure", "tell me more", "what's the offer", "how much", "send", "contract", "deal")
        not_interested = ("not interested", "no thanks", "stop calling", "remove", "don't call", "not selling", "keep it")
        response_lower = response.lower()
        if any(w in response_lower for w in not_interested):
            session.outcome = "not_interested"
            session.status = "completed"
            return "I understand. I'll remove you from our list. Thank you for your time."
        if any(w in response_lower for w in interested_words):
            session.outcome = "interested"
        return self.get_next_script(session_id)

    def complete_call(self, session_id: str) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if not session:
            return {"error": "Session not found"}
        session.status = "completed"
        session.end_time = datetime.now(timezone.utc).isoformat()
        return {"call_id": session.call_id, "lead_id": session.lead_id, "outcome": session.outcome or "completed", "transcript_length": len(session.transcript), "phase_reached": session.current_phase, "questions_asked": session.current_question}

    def _get_lead(self, session: CallSession) -> VacantLandLead | Any:
        return self._leads.get(session.lead_id, VacantLandLead())

    def _negotiation_tip(self, lead: VacantLandLead) -> str:
        if lead.deal_score >= 6:
            return "If their asking price is significantly lower, we can lock them between $5K-$15K under asking."
        return "We're flexible on terms."
