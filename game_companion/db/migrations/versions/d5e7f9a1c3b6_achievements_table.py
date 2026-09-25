"""achievements table (delight pass): per-player unlocked milestones.

Revision ID: d5e7f9a1c3b6
Revises: c8f4a2b6d9e1
Create Date: 2026-09-25

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

import game_companion.db.base as gcdb

revision: str = "d5e7f9a1c3b6"
down_revision: str | None = "c8f4a2b6d9e1"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "achievements",
        sa.Column("player_profile_id", sa.String(length=32), nullable=False),
        sa.Column("game_id", sa.String(length=40), nullable=False),
        sa.Column("key", sa.String(length=60), nullable=False),
        sa.Column("unlocked_at", gcdb.UTCDateTime(), nullable=True),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", gcdb.UTCDateTime(), nullable=False),
        sa.Column("updated_at", gcdb.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["player_profile_id"], ["player_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("player_profile_id", "game_id", "key", name="uq_achievement"),
    )
    with op.batch_alter_table("achievements", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_achievements_player_profile_id"), ["player_profile_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_achievements_game_id"), ["game_id"], unique=False)


def downgrade() -> None:
    op.drop_table("achievements")
