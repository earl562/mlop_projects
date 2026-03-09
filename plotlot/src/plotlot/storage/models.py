"""SQLAlchemy ORM models for pgvector storage."""

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, JSON, TSVECTOR
from sqlalchemy.orm import DeclarativeBase


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

    id = Column(Integer, primary_key=True, autoincrement=True)
    municipality = Column(String(200), nullable=False, index=True)
    county = Column(String(100), nullable=False, index=True)
    chapter = Column(String(500))
    section = Column(String(200))
    section_title = Column(String(500))
    zone_codes: Column = Column(ARRAY(String), default=[])
    chunk_text = Column(Text, nullable=False)
    chunk_index = Column(Integer, default=0)
    embedding = Column(Vector(1024))
    municode_node_id = Column(String(200))
    search_vector = Column(TSVECTOR)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class PortfolioEntry(Base):
    """A saved zoning analysis in the user's portfolio.

    Persists portfolio data across server restarts. The user_id column is
    nullable until auth (Supabase) is wired in — enables per-user filtering
    once authentication is enabled.
    """

    __tablename__ = "portfolio_entries"

    id = Column(Integer, primary_key=True)
    user_id = Column(String, nullable=True, index=True)  # nullable until auth is wired in
    address = Column(String, nullable=False)
    municipality = Column(String, nullable=False)
    county = Column(String, nullable=False)
    zoning_district = Column(String, nullable=True)
    report_json = Column(JSON, nullable=False)  # full ZoningReportResponse as dict
    notes = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )


class ReportCache(Base):
    """Cached zoning report to avoid redundant LLM calls for repeated addresses.

    Reports are stored as JSON with a TTL (default 24h). The address_normalized
    column provides a unique, deterministic cache key derived from the raw address.
    """

    __tablename__ = "report_cache"

    id = Column(Integer, primary_key=True)
    address = Column(String, nullable=False, index=True)
    address_normalized = Column(String, nullable=False, unique=True)  # lowercase, stripped
    report_json = Column(JSON, nullable=False)  # full ZoningReportResponse as dict
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)  # TTL
    hit_count = Column(Integer, default=0)
