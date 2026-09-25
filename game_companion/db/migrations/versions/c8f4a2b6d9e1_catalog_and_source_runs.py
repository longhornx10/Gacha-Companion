"""Catalog + source-run tables (M25).

Revision ID: c8f4a2b6d9e1
Revises: b7e3a9c1d2f4
Create Date: 2026-09-24

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

import game_companion.db.base as gcdb

revision: str = "c8f4a2b6d9e1"
down_revision: str | None = "b7e3a9c1d2f4"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "game_catalog",
        sa.Column("game_id", sa.String(length=40), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("rarity", sa.Integer(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("source", sa.String(length=60), nullable=True),
        sa.Column("fetched_at", gcdb.UTCDateTime(), nullable=True),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", gcdb.UTCDateTime(), nullable=False),
        sa.Column("updated_at", gcdb.UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", "entity_type", "key", name="uq_catalog_entity"),
    )
    with op.batch_alter_table("game_catalog", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_game_catalog_game_id"), ["game_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_game_catalog_entity_type"), ["entity_type"], unique=False
        )

    op.create_table(
        "source_runs",
        sa.Column("game_id", sa.String(length=40), nullable=False),
        sa.Column("source_key", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("items", sa.Integer(), nullable=False),
        sa.Column("fetched_at", gcdb.UTCDateTime(), nullable=True),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", gcdb.UTCDateTime(), nullable=False),
        sa.Column("updated_at", gcdb.UTCDateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("game_id", "source_key", name="uq_source_run"),
    )
    with op.batch_alter_table("source_runs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_source_runs_game_id"), ["game_id"], unique=False)


def downgrade() -> None:
    op.drop_table("source_runs")
    op.drop_table("game_catalog")
