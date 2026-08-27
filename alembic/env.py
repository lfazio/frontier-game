from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

from frontier.adapters.db.models import Base
from frontier.config.settings import Settings

config = context.config
config.set_main_option("sqlalchemy.url", Settings().database_url)
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"),
                      target_metadata=target_metadata, literal_binds=True,
                      include_schemas=True, version_table_schema="core")
    with context.begin_transaction():
        context.run_migrations()


def _do_run(connection: object) -> None:
    # The version table lives in `core`, so the schema must exist before Alembic bootstraps it.
    connection.execute(text("CREATE SCHEMA IF NOT EXISTS core"))  # type: ignore[attr-defined]
    context.configure(connection=connection, target_metadata=target_metadata,  # type: ignore[arg-type]
                      include_schemas=True, version_table_schema="core")
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = async_engine_from_config(config.get_section(config.config_ini_section, {}),
                                      prefix="sqlalchemy.", poolclass=NullPool)
    async with engine.connect() as connection:
        await connection.run_sync(_do_run)
        await connection.commit()
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
