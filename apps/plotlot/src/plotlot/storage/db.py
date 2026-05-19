"""Async database engine and session factory.

Provides a single engine per process with lazy initialization.
All consumers go through get_session() for connection management.

The asyncpg engine is bound to the running event loop. Test suites and worker
processes may create fresh loops between calls, so we rebuild the engine when
the active loop changes instead of reusing a stale pooled connection.
"""

import asyncio
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from plotlot.config import settings
from plotlot.storage.models import Base

logger = logging.getLogger(__name__)

_engine = None
_session_factory = None
_engine_loop_id = None


def _current_loop_id() -> int | None:
    try:
        return id(asyncio.get_running_loop())
    except RuntimeError:
        return None


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
        # Neon free tier: 5 max connections. Keep pool small to avoid
        # exhaustion during batch ingestion (DDIA: bounded resources).
        _engine = create_async_engine(
            settings.database_url,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_size=2,
            max_overflow=1,
            pool_timeout=30,
            **kwargs,
        )
    return _engine


async def _ensure_engine():
    global _engine, _session_factory, _engine_loop_id

    current_loop_id = _current_loop_id()
    if (
        _engine is not None
        and _engine_loop_id is not None
        and current_loop_id is not None
        and _engine_loop_id != current_loop_id
    ):
        try:
            await _engine.dispose()
        except Exception:
            logger.warning("Failed to dispose stale async engine", exc_info=True)
        _engine = None
        _session_factory = None
        _engine_loop_id = None

    if _engine is None:
        _engine = _get_engine()
        _engine_loop_id = current_loop_id

    return _engine


async def init_db() -> None:
    """Create all tables and install triggers if they don't exist."""
    engine = await _ensure_engine()
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        await conn.run_sync(Base.metadata.create_all)

        # Auto-populate search_vector on INSERT/UPDATE via trigger
        await conn.execute(
            text("""
            CREATE OR REPLACE FUNCTION ordinance_chunks_search_vector_update()
            RETURNS trigger AS $$
            BEGIN
                NEW.search_vector := to_tsvector('english', COALESCE(NEW.chunk_text, ''));
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;
        """)
        )
        await conn.execute(
            text("""
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
        """)
        )
        # GIN index for fast full-text search
        await conn.execute(
            text("""
            CREATE INDEX IF NOT EXISTS idx_search_vector
            ON ordinance_chunks USING GIN (search_vector);
        """)
        )

    logger.info("Database initialized")


async def get_session() -> AsyncSession:
    """Get an async database session."""
    global _session_factory
    await _ensure_engine()
    if _session_factory is None:
        _session_factory = async_sessionmaker(_get_engine(), expire_on_commit=False)
    return _session_factory()
