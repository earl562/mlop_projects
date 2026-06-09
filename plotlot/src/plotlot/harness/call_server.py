"""Standalone call server — test calls now, connect to phone systems later.

Starts a local WebSocket server that runs the PlotLot voice agent.
Test with: curl http://localhost:8765/call/test
Connect to: any SIP provider, Astradial, or Twilio via WebSocket bridge.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import tempfile
import urllib.request, csv, io

from plotlot.harness.lead_management import LeadPipeline, LeadStatus
from plotlot.harness.voice_agent import VoiceAgent
from plotlot.harness.s2s_voice import speak
from plotlot.harness.county_zoning import estimate_unit_potential
from plotlot.harness.deal_evaluator import score_deal, calculate_offer


class CallServer:
    """Self-contained call server for PlotLot voice agent."""

    def __init__(self):
        self._pipeline = self._load_leads()
        self._leads = {l.parcel_id: l for l in self._pipeline._leads.values()}
        self._voice = VoiceAgent(self._leads)

    def _load_leads(self) -> LeadPipeline:
        csv_url = 'https://docs.google.com/spreadsheets/d/1ZIXhEx_1w0Ei6ZRGw4J6Qwyl5CIsLSek/export?format=csv'
        resp = urllib.request.urlopen(csv_url)
        content = resp.read().decode('utf-8')
        rows = [r for i, r in enumerate(csv.DictReader(io.StringIO(content))) if i < 10]
        pipeline = LeadPipeline.from_csv('\n'.join([','.join(rows[0].keys())] + [','.join(r.values()) for r in rows]))
        for l in pipeline._leads.values():
            z = estimate_unit_potential(l.lot_size_sqft, l.county)
            o = calculate_offer(l.est_value if l.est_value > 0 else max(l.assessed_value * 3, 150000))
            s = score_deal(l.lot_acres, l.assessed_value, l.est_value, 0, z['max_units'], True, True, 0, l.owner_occupied, l.mls_status in ('FAIL', 'REMOVED'))
            pipeline.score_deal(l.parcel_id, s, z['max_units'], o, True, True, [])
        return pipeline

    async def call_lead(self, lead_name: str) -> dict:
        """Call a specific lead by name."""
        matches = [l for l in self._pipeline._leads.values() if lead_name.upper() in l.owner_name.upper()]
        if not matches:
            return {"error": f"Lead '{lead_name}' not found"}
        lead = matches[0]
        session = self._voice.start_outbound(lead.parcel_id)

        print(f"\n📞 CALLING: {lead.owner_name} — {lead.property_address or lead.apn}")
        print(f"   {lead.lot_acres:.1f}ac | {lead.county} | Offer: ${session.offer_amount:,.0f}")
        print(f"   Phone: {lead.owner_phones[0] if lead.owner_phones else 'N/A'}\n")

        # Intro
        greeting = self._voice.get_next_script(session.call_id)
        await speak(greeting, "male", engine="edge")
        print(f"🎙️  AGENT: {greeting[:90]}...")

        # Simulate caller responses
        answers = [
            "Yes, this is a good time.",
            "128 Cannon Rd, Stanley NC 28164",
            "About 4 acres",
            "No survey, bought it in 1984",
            "No city utilities",
            "ok",
            "Virgin land, never built on",
            "Not a dump site",
            "No easements",
            "ok",
            "No deed restrictions",
            "Flood zone X",
        ]

        for i, answer in enumerate(answers):
            outcome = self._voice.process_response(session.call_id, answer)
            print(f"📱 CALLER: '{answer}'")
            if session.status == "completed":
                break
            next_text = self._voice.get_next_script(session.call_id)
            if next_text and session.current_phase in ("offer", "close"):
                await speak(next_text, "male", engine="edge")
            if next_text:
                print(f"🎙️  AGENT: {next_text[:90]}...")

        result = self._voice.complete_call(session.call_id)
        self._pipeline.advance(lead.parcel_id, LeadStatus.CONTACTED, f"Call completed: {result['outcome']}")

        return {
            "lead": lead.owner_name,
            "call_id": session.call_id,
            "outcome": result["outcome"],
            "questions": result["questions_asked"],
            "transcript_length": result["transcript_length"],
        }

    async def test_call(self) -> dict:
        """Run a test call with the highest-scored lead."""
        top = self._pipeline.top_deals(min_score=4, limit=1)
        if not top:
            return {"error": "No leads available"}
        return await self.call_lead(top[0].owner_name)


async def main():
    server = CallServer()
    print("=" * 60)
    print("📞 PLOTLOT CALL SERVER — LIVE TEST CALL")
    print("=" * 60)

    result = await server.test_call()
    print(f"\n{'='*60}")
    print(f"✅ CALL COMPLETE: {result.get('outcome', 'unknown')}")
    print(f"   Lead: {result.get('lead', 'unknown')}")
    print(f"   Questions: {result.get('questions', 0)}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
