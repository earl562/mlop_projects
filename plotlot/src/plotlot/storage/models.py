"""SQLAlchemy ORM models for pgvector storage."""

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, TSVECTOR
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class OrdinanceChunk(Base):
    """A chunk of zoning ordinance text with its embedding vector."""

    __tablename__ = "ordinance_chunks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    municipality = Column(String(200), nullable=False, index=True)
    county = Column(String(100), nullable=False, index=True)
    chapter = Column(String(500))
    section = Column(String(200))
    section_title = Column(String(500))
    zone_codes = Column(ARRAY(String), default=[])
    chunk_text = Column(Text, nullable=False)
    chunk_index = Column(Integer, default=0)
    embedding = Column(Vector(1024))
    municode_node_id = Column(String(200))
    search_vector = Column(TSVECTOR)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
