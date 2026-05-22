"""Unit tests for core types and validation."""
from __future__ import annotations

import pytest
from outreach.core.types import (
    Channel,
    ICPType,
    Prospect,
    ProspectStatus,
    PitchContext,
    Event,
    EventStatus,
)


def test_prospect_defaults():
    p = Prospect(
        name="John Doe",
        first_name="John",
        last_name="Doe",
        title="VP Land Acquisition",
        company="D.R. Horton",
        market="NorCal",
        icp_type=ICPType.RESIDENTIAL,
    )
    assert p.status == ProspectStatus.QUEUED
    assert p.email is None
    assert p.email_verified is False


def test_prospect_icp_types():
    for icp in ICPType:
        p = Prospect(
            name="Test", first_name="Test", last_name="User",
            title="Title", company="Co", market="Bay Area", icp_type=icp,
        )
        assert p.icp_type == icp


def test_pitch_context_char_limit():
    p = Prospect(
        name="Jane Smith", first_name="Jane", last_name="Smith",
        title="Land Acquisition Manager", company="Lennar",
        market="Bay Area", icp_type=ICPType.RESIDENTIAL,
    )
    ctx = PitchContext(
        prospect=p,
        channel=Channel.LINKEDIN,
        plotlot_demo_url="https://plotlot.app",
        plotlot_counties="Santa Clara, Alameda",
        char_limit=200,
    )
    assert ctx.char_limit == 200
    assert ctx.channel == Channel.LINKEDIN


def test_event_defaults():
    ev = Event(name="ULI Spring Forum", organizer="ULI", location="San Francisco, CA")
    assert ev.status == EventStatus.DISCOVERED
    assert ev.relevance_score == 0.0


def test_channel_enum_values():
    assert Channel.EMAIL.value == "email"
    assert Channel.LINKEDIN.value == "linkedin"
    assert Channel.TWITTER.value == "twitter"


def test_prospect_status_transitions():
    statuses = [s.value for s in ProspectStatus]
    assert "queued" in statuses
    assert "email_sent" in statuses
    assert "replied" in statuses
    assert "demo_scheduled" in statuses
