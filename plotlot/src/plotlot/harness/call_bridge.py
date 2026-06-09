"""Call bridge — connects PlotLot voice agent to phone systems (Astradial, SIP, WebSocket).

Architecture:
    Phone System (Astradial/SIP) ←→ WebSocket ←→ Voice Agent ←→ OpenRouter LLM

Flow:
    1. Incoming call → matched to lead by phone number
    2. Voice agent runs full sales script via edge-tts (natural voice)
    3. Caller audio transcribed via faster-whisper (or simulated)
    4. Agent responds with next script question
    5. Call completes → outcome logged to pipeline

Usage:
    python call_bridge.py --port 8765
    # Then point Astradial AI bot WebSocket to ws://localhost:8765/call
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tempfile
from typing import Any

from plotlot.harness.voice_agent import VoiceAgent, CallSession
from plotlot.harness.lead_management import LeadPipeline, VacantLandLead, LeadStatus
from plotlot.harness.s2s_voice import speak
from plotlot.harness.model_adapter import create_model_caller


class CallBridge:
    """WebSocket bridge between phone system and PlotLot voice agent."""

    def __init__(self, pipeline: LeadPipeline):
        self._pipeline = pipeline
        self._leads = {l.parcel_id: l for l in pipeline._leads.values()}
        self._voice = VoiceAgent(self._leads)
        self._active_calls: dict[str, CallSession] = {}

    def match_caller(self, phone: str) -> VacantLandLead | None:
        """Match incoming phone number to a lead."""
        clean = phone.replace("-", "").replace(" ", "").replace("(", "").replace(")", "")[-10:]
        for lead in self._leads.values():
            for p in lead.owner_phones:
                if p.replace("-", "").replace(" ", "")[-10:] == clean:
                    return lead
        return None

    async def handle_incoming_call(self, caller_phone: str, caller_name: str = "") -> dict[str, Any]:
        """Handle an incoming call. Returns initial greeting audio and call metadata."""
        lead = self.match_caller(caller_phone)
        if lead:
            session = self._voice.start_outbound(lead.parcel_id)
            self._active_calls[session.call_id] = session
            greeting = f"Hi {lead.owner_first}, this is Earl with ESP and ME LLC. I'm calling about the property at {lead.property_address or lead.apn}. Is this a good time to talk?"
            audio_path = await speak(greeting, "male", engine="edge")
            return {
                "matched": True,
                "call_id": session.call_id,
                "lead_name": lead.owner_name,
                "property": lead.property_address or lead.apn,
                "lot_acres": lead.lot_acres,
                "greeting_audio": audio_path,
                "greeting_text": greeting,
            }
        else:
            greeting = "Hi, this is Earl with ESP and ME LLC. I'm calling about a property. Who am I speaking with?"
            audio_path = await speak(greeting, "male", engine="edge")
            return {
                "matched": False,
                "call_id": f"unknown-{caller_phone[-4:]}",
                "greeting_audio": audio_path,
                "greeting_text": greeting,
            }

    async def process_caller_response(self, call_id: str, caller_text: str) -> dict[str, Any]:
        """Process caller's response and return next agent message."""
        session = self._active_calls.get(call_id)
        if not session:
            return {"error": "Call not found", "done": True}

        outcome = self._voice.process_response(call_id, caller_text)

        if session.status == "completed":
            result = self._voice.complete_call(call_id)
            close_text = "Thank you for your time. Have a great day!"
            audio_path = await speak(close_text, "male", engine="edge")
            return {
                "done": True,
                "outcome": result["outcome"],
                "agent_text": close_text,
                "agent_audio": audio_path,
                "questions_asked": result["questions_asked"],
            }

        next_script = self._voice.get_next_script(call_id)
        audio_path = await speak(next_script, "male", engine="edge")
        return {
            "done": False,
            "agent_text": next_script,
            "agent_audio": audio_path,
            "phase": session.current_phase if session else "unknown",
            "outcome": session.outcome if session else "",
        }

    async def run_full_call_simulation(self, lead: VacantLandLead, caller_responses: list[str] | None = None) -> dict[str, Any]:
        """Run a complete simulated call for testing."""
        session = self._voice.start_outbound(lead.parcel_id)
        self._active_calls[session.call_id] = session

        transcript = []
        # Initial greeting
        greeting = self._voice.get_next_script(session.call_id)
        transcript.append({"speaker": "agent", "text": greeting})

        responses = caller_responses or ["yes", "ok", "sure", "no", "ok", "ok", "ok", "ok", "ok", "ok"]
        for resp in responses:
            self._voice.process_response(session.call_id, resp)
            transcript.append({"speaker": "caller", "text": resp})

            if session.status == "completed":
                break

            next_text = self._voice.get_next_script(session.call_id)
            if next_text:
                transcript.append({"speaker": "agent", "text": next_text})

        result = self._voice.complete_call(session.call_id)
        return {
            "call_id": session.call_id,
            "lead_name": lead.owner_name,
            "outcome": result["outcome"],
            "questions_asked": result["questions_asked"],
            "transcript": transcript,
        }

    def active_calls(self) -> list[dict[str, Any]]:
        return [
            {"call_id": s.call_id, "lead_name": s.lead_name, "status": s.status, "phase": s.current_phase, "outcome": s.outcome}
            for s in self._active_calls.values()
        ]
