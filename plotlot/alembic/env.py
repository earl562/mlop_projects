"""Alembic environment configuration for PlotLot.

Supports async migration via asyncpg. Imports the application's models
so autogenerate can detect schema changes against the ORM.
"""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool, text
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from plotlot.config import settings
from plotlot.storage.models import Base  # noqa: F401 — registers all models

# Alembic Config object — provides access to alembic.ini values
config = context.config

# Override sqlalchemy.url from application settings (asyncpg driver)
config.set_main_option("sqlalchemy.url", settings.database_url)

# Set up Python logging from the .ini file
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate support
target_metadata = Base.metadata


def guard_ambiguous_legacy_revision(connection: Connection) -> None:
    version_table = connection.execute(
        text("SELECT to_regclass('public.alembic_version')")
    ).scalar_one()
    if version_table is None:
        return
    current_revisions = set(
        connection.execute(text("SELECT version_num FROM alembic_version")).scalars()
    )
    ambiguous = current_revisions.intersection({"007", "008"})
    if ambiguous:
        revisions = ", ".join(sorted(ambiguous))
        raise RuntimeError(
            "Automatic migration blocked: alembic_version reports ambiguous "
            f"legacy revision(s) {revisions}. Perform a manual schema audit "
            "before stamping the proven revision lineage."
        )


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Generates SQL scripts without connecting to the database.
    Useful for reviewing migration SQL before applying.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations using the provided connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        # Render pgvector Vector type correctly
        render_as_batch=False,
    )

    with context.begin_transaction():
        guard_ambiguous_legacy_revision(connection)
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with an async engine.

    Creates an async engine from the alembic config and runs
    migrations within a connection context.
    """
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online migrations — delegates to async runner."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
