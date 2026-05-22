"""Unit tests for DB schema — uses in-memory SQLite."""
from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from outreach.core.db import Base, ProspectRow, OutreachMessageRow, EventRow


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


async def test_prospect_insert(session: AsyncSession):
    row = ProspectRow(
        name="John Jarecki",
        first_name="John",
        last_name="Jarecki",
        title="VP Land Acquisition",
        company="D.R. Horton",
        market="NorCal",
        icp_type="residential",
        linkedin_url="https://linkedin.com/in/johnjarecki",
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    assert row.id is not None
    assert row.status == "queued"
    assert row.email_verified is False


async def test_outreach_message_insert(session: AsyncSession):
    prospect = ProspectRow(
        name="Jason Jones", first_name="Jason", last_name="Jones",
        title="Land Acquisition", company="Lennar", market="Bay Area", icp_type="residential",
    )
    session.add(prospect)
    await session.flush()

    msg = OutreachMessageRow(
        prospect_id=prospect.id,
        channel="email",
        subject="PlotLot — density calc for Bay Area land acq",
        body="Hi Jason, ...",
        status="sent",
    )
    session.add(msg)
    await session.commit()
    await session.refresh(msg)
    assert msg.id is not None
    assert msg.channel == "email"


async def test_event_insert(session: AsyncSession):
    ev = EventRow(
        name="ULI Spring Forum",
        organizer="ULI",
        location="San Francisco, CA",
        relevance_score=0.85,
    )
    session.add(ev)
    await session.commit()
    await session.refresh(ev)
    assert ev.id is not None
    assert ev.status == "discovered"
    assert ev.relevance_score == 0.85
