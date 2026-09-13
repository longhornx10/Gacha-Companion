"""Alembic helpers shared by CLI and tests."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

MIGRATIONS_DIR = Path(__file__).resolve().parent


def make_alembic_config(database_url: str | None = None) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    if database_url:
        cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def upgrade_to_head(database_url: str | None = None) -> None:
    """Create/upgrade the schema at ``database_url`` (settings default if None)."""
    import os

    if database_url is None:
        from game_companion.config import get_settings

        settings = get_settings()
        database_url = settings.resolved_database_url
        Path(settings.resolved_data_dir).mkdir(parents=True, exist_ok=True)
    os.environ["ALEMBIC_DATABASE_URL"] = database_url
    command.upgrade(make_alembic_config(database_url), "head")
