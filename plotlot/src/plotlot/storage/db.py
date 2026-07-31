"""Async database engine and session factory.

Provides a single engine per process with lazy initialization.
All consumers go through get_session() for connection management.

The asyncpg engine is bound to the running event loop. Test suites and worker
processes may create fresh loops between calls, so we rebuild the engine when
the active loop changes instead of reusing a stale pooled connection.
"""

import logging

import anyio
from sqlalchemy import event, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, SessionTransaction

from plotlot.config import settings
from plotlot.security.context import current_tenant_id
from plotlot.storage.model_base import Base

logger = logging.getLogger(__name__)

_engine = None
_session_factory = None
_engine_loop_id = None
_engine_lock = anyio.Lock()


@event.listens_for(Session, "after_begin")
def _set_transaction_tenant(
    _session: Session,
    _transaction: SessionTransaction,
    connection: Connection,
) -> None:
    tenant_id = current_tenant_id()
    if tenant_id is not None:
        connection.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": tenant_id},
        )


def _current_loop_id() -> int | None:
    try:
        return id(anyio.lowlevel.current_token())
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

    async with _engine_lock:
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


def _detect_schema_drift(sync_conn) -> list[str]:
    """Return human-readable drift between the ORM models and the live schema.

    `Base.metadata.create_all` only ever CREATEs tables that do not exist — it
    never ALTERs an existing table. So when a model gains a column, an already
    created table silently keeps the old shape and every insert/select against
    that column fails at runtime (this is exactly how workspaces.owner_user_id
    went missing and broke the harness persistence path for weeks).

    This check turns that silent divergence into a loud startup warning. It only
    reports things the app itself declares and is missing from the database;
    extra tables/columns are ignored on purpose because this database is shared
    with MLflow and other apps whose tables are not in our metadata.
    """
    from sqlalchemy import inspect

    inspector = inspect(sync_conn)
    existing_tables = set(inspector.get_table_names())
    problems: list[str] = []

    for table_name, table in Base.metadata.tables.items():
        if table_name not in existing_tables:
            problems.append(f"missing table: {table_name}")
            continue
        db_columns = {c["name"] for c in inspector.get_columns(table_name)}
        missing = sorted(set(table.columns.keys()) - db_columns)
        if missing:
            problems.append(f"{table_name} missing columns: {', '.join(missing)}")

    return problems


async def init_db() -> None:
    """Verify database connectivity after externally managed migrations.

    Schema is owned by Alembic (`alembic upgrade head`), not by this function —
    creating tables here would silently diverge from the migration history. The
    drift check below is the guard for exactly that: it reports, without ever
    blocking startup, any table or column the models declare that the live
    database lacks, which is the signature of a migration that was never run.
    """
    engine = await _ensure_engine()
    async with engine.connect() as conn:
        logger.info("Database connection verified")

        # Never fatal: a degraded-but-running API beats refusing to boot, and the
        # operator needs the log line to know a migration is owed.
        try:
            drift = await conn.run_sync(_detect_schema_drift)
        except Exception:
            logger.warning("Schema drift check failed to run", exc_info=True)
            drift = []
        if drift:
            logger.error(
                "SCHEMA DRIFT DETECTED (%d) — the live database is behind the models; "
                "run `alembic upgrade head`. Details: %s",
                len(drift),
                "; ".join(drift),
            )

    from plotlot.storage.runtime import initialize_configured_storage_runtime

    await initialize_configured_storage_runtime()


async def get_session() -> AsyncSession:
    """Get an async database session."""
    global _session_factory
    await _ensure_engine()
    if _session_factory is None:
        _session_factory = async_sessionmaker(_get_engine(), expire_on_commit=False)
    return _session_factory()
