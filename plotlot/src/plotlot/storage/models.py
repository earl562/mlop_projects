"""SQLAlchemy ORM models for pgvector storage."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSON, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class OrdinanceChunk(Base):
    """A chunk of zoning ordinance text with its embedding vector."""

    __tablename__ = "ordinance_chunks"
    __table_args__ = (
        UniqueConstraint(
            "municipality",
            "municode_node_id",
            "chunk_index",
            name="uq_chunk_natural_key",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    municipality: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    county: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    chapter: Mapped[str | None] = mapped_column(String(500))
    section: Mapped[str | None] = mapped_column(String(200))
    section_title: Mapped[str | None] = mapped_column(String(500))
    zone_codes: Mapped[list[str] | None] = mapped_column(ARRAY(String), default=[])
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    embedding: Mapped[Any | None] = mapped_column(Vector(1024))
    municode_node_id: Mapped[str | None] = mapped_column(String(200))
    search_vector: Mapped[Any | None] = mapped_column(TSVECTOR)

    # Lineage fields (B2) — provenance tracking for each chunk
    source_url: Mapped[str | None] = mapped_column(String, nullable=True)
    scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    embedding_model: Mapped[str | None] = mapped_column(String, nullable=True)

    # State/region field (B6) — supports multi-state expansion (FL, NC, etc.)
    state: Mapped[str | None] = mapped_column(String(2), nullable=True, default="FL")

    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class IngestionCheckpoint(Base):
    """Tracks per-municipality ingestion progress for resumable batch jobs.

    DDIA pattern: idempotent writes with checkpointing. Each municipality
    is a partition — failures are isolated, progress is persistent, and
    the pipeline resumes from where it left off.
    """

    __tablename__ = "ingestion_checkpoints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    municipality_key: Mapped[str] = mapped_column(String(100), nullable=False)
    state: Mapped[str] = mapped_column(String(2), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending|running|complete|failed
    chunks_stored: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("batch_id", "municipality_key", name="uq_checkpoint_batch_muni"),
    )


class PortfolioEntry(Base):
    """A saved zoning analysis in the user's portfolio.

    Persists portfolio data across server restarts. The user_id column is
    nullable until auth (Supabase) is wired in — enables per-user filtering
    once authentication is enabled.
    """

    __tablename__ = "portfolio_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    address: Mapped[str] = mapped_column(String, nullable=False)
    municipality: Mapped[str] = mapped_column(String, nullable=False)
    county: Mapped[str] = mapped_column(String, nullable=False)
    zoning_district: Mapped[str | None] = mapped_column(String, nullable=True)
    report_json: Mapped[Any] = mapped_column(JSON, nullable=False)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class ReportCache(Base):
    """Cached zoning report to avoid redundant LLM calls for repeated addresses.

    Reports are stored as JSON with a TTL (default 24h). The composite key
    (address_normalized, analysis_type) ensures residential and data center
    analyses on the same address are cached independently.
    """

    __tablename__ = "report_cache"
    __table_args__ = (
        UniqueConstraint("address_normalized", "analysis_type", name="uq_report_cache_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    address: Mapped[str] = mapped_column(String, nullable=False, index=True)
    address_normalized: Mapped[str] = mapped_column(String, nullable=False)
    analysis_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="residential"
    )  # residential|datacenter
    report_json: Mapped[Any] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, default=0)


class ConnectorCredential(Base):
    """SMTP credentials for the Outreach connector, encrypted at rest with Fernet.

    Keyed by session_id (same value stored in plotlot_backend_session localStorage).
    No user accounts required — session-scoped, single owner per session.
    """

    __tablename__ = "connector_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)

    # SMTP settings
    smtp_host: Mapped[str] = mapped_column(String(255), nullable=False)
    smtp_port: Mapped[int] = mapped_column(Integer, nullable=False, default=587)
    smtp_username: Mapped[str] = mapped_column(String(255), nullable=False)
    smtp_password_enc: Mapped[str] = mapped_column(Text, nullable=False)

    # From header
    from_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Anti-spam: rolling daily counter, reset_at marks start of the current window
    daily_send_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    send_count_reset_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class UserSubscription(Base):
    """Tracks each user's plan tier and monthly analysis usage.

    Created on first authenticated request.  ``analyses_used`` resets monthly
    via Stripe ``invoice.paid`` webhook or when ``period_end`` has passed.
    """

    __tablename__ = "user_subscriptions"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    plan: Mapped[str] = mapped_column(String, default="free", nullable=False)
    stripe_customer_id: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String, nullable=True)
    analyses_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
