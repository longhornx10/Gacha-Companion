"""Alembic migration environment.

The database URL comes from Gacha Companion settings (env prefix
``GAME_COMPANION_``), or from the ALEMBIC_DATABASE_URL env var override used
by tests and tooling.
"""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import pool

from game_companion.db.base import Base
from game_companion.db.models import *  # noqa: F401,F403 - register all tables

config = context.config


def _database_url() -> str:
    override = os.environ.get("ALEMBIC_DATABASE_URL")
    if override:
        return override
    from game_companion.config import get_settings

    return get_settings().resolved_database_url


# Custom type rendering: reference game_companion.db.base as gcdb (imported in
# the script template).
_GCDB_PREFIX = "gcdb."


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        user_module_prefix=_GCDB_PREFIX,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    from sqlalchemy import create_engine

    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=Base.metadata,
            render_as_batch=True,  # SQLite-friendly ALTERs
            user_module_prefix=_GCDB_PREFIX,
        )
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
