"""Async database engine and session factory.

Provides a single engine per process with lazy initialization.
All consumers go through get_session() for connection management.
"""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from plotlot.config import settings
from plotlot.storage.models import Base

logger = logging.getLogger(__name__)

_engine = None
_session_factory = None


def _get_engine():
    global _engine
    if _engine is None:
        kwargs: dict = {"echo": False}
        connect_args: dict = {"timeout": 10}  # 10s connection timeout for asyncpg
        if settings.database_require_ssl:
            import ssl

            ctx = ssl.create_default_context()
            connect_args["ssl"] = ctx
        kwargs["connect_args"] = connect_args
        _engine = create_async_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_recycle=300,
            **kwargs,
        )
    return _engine


async def init_db() -> None:
    """Create all tables and install triggers if they don't exist."""
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        await conn.run_sync(Base.metadata.create_all)

        # Auto-populate search_vector on INSERT/UPDATE via trigger
        await conn.execute(text("""
            CREATE OR REPLACE FUNCTION ordinance_chunks_search_vector_update()
            RETURNS trigger AS $$
            BEGIN
                NEW.search_vector := to_tsvector('english', COALESCE(NEW.chunk_text, ''));
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """))
        await conn.execute(text("""
            DO $$ BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_trigger WHERE tgname = 'trg_search_vector_update'
                ) THEN
                    CREATE TRIGGER trg_search_vector_update
                    BEFORE INSERT OR UPDATE OF chunk_text
                    ON ordinance_chunks
                    FOR EACH ROW
                    EXECUTE FUNCTION ordinance_chunks_search_vector_update();
                END IF;
            END $$;
        """))
        # GIN index for fast full-text search
        await conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_search_vector
            ON ordinance_chunks USING GIN (search_vector);
        """))

    logger.info("Database initialized")


async def get_session() -> AsyncSession:
    """Get an async database session."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(_get_engine(), expire_on_commit=False)
    return _session_factory()
