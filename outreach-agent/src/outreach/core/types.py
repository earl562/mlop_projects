from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, EmailStr


class ICPType(str, Enum):
    RESIDENTIAL = "residential"   # homebuilders, land acq VPs
    DATACENTER = "datacenter"     # energy, infrastructure site originators
    PRESS = "press"               # journalists, CRE media
    INVESTOR = "investor"         # multifamily, infill investors


class Channel(str, Enum):
    EMAIL = "email"
    LINKEDIN = "linkedin"
    TWITTER = "twitter"


class ProspectStatus(str, Enum):
    QUEUED = "queued"             # discovered, not yet contacted
    EMAIL_SENT = "email_sent"
    LINKEDIN_SENT = "linkedin_sent"
    TWITTER_SENT = "twitter_sent"
    CONNECTED = "connected"       # LinkedIn accepted
    REPLIED = "replied"           # any positive response
    DEMO_SCHEDULED = "demo_scheduled"
    DEAD = "dead"                 # bounced, ignored, not a fit


class EventStatus(str, Enum):
    DISCOVERED = "discovered"
    ATTENDING = "attending"
    ATTENDED = "attended"
    SKIPPED = "skipped"


class Prospect(BaseModel):
    id: Optional[int] = None
    name: str
    first_name: str
    last_name: str
    title: str
    company: str
    market: str                   # e.g. "Bay Area", "Sacramento", "NorCal"
    icp_type: ICPType
    email: Optional[str] = None
    email_verified: bool = False
    linkedin_url: Optional[str] = None
    twitter_handle: Optional[str] = None
    status: ProspectStatus = ProspectStatus.QUEUED
    notes: Optional[str] = None
    source: Optional[str] = None  # where we found them
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class OutreachMessage(BaseModel):
    id: Optional[int] = None
    prospect_id: int
    channel: Channel
    subject: Optional[str] = None
    body: str
    status: str = "drafted"       # drafted | sent | delivered | replied | bounced
    sent_at: Optional[datetime] = None
    replied_at: Optional[datetime] = None
    error: Optional[str] = None
    created_at: Optional[datetime] = None


class Event(BaseModel):
    id: Optional[int] = None
    name: str
    organizer: str                # ULI, BIA Bay Area, NAIOP, etc.
    date: Optional[datetime] = None
    location: str
    url: Optional[str] = None
    description: Optional[str] = None
    relevance_score: float = 0.0  # 0-1 — how well it matches PlotLot ICP
    status: EventStatus = EventStatus.DISCOVERED
    created_at: Optional[datetime] = None


class PitchContext(BaseModel):
    """Context passed to Claude when generating a personalized pitch."""
    prospect: Prospect
    channel: Channel
    plotlot_demo_url: str
    plotlot_counties: str
    char_limit: Optional[int] = None  # LinkedIn 200-char connection note
