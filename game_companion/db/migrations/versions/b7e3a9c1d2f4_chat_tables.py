"""Chat tables (M22): conversations, messages, companion memories.

Revision ID: b7e3a9c1d2f4
Revises: a1f2c3d4e5b6
Create Date: 2026-09-23

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

import game_companion.db.base as gcdb

revision: str = "b7e3a9c1d2f4"
down_revision: str | None = "a1f2c3d4e5b6"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("game_id", sa.String(length=40), nullable=False),
        sa.Column("player_profile_id", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("persona_id", sa.String(length=80), nullable=True),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", gcdb.UTCDateTime(), nullable=False),
        sa.Column("updated_at", gcdb.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["player_profile_id"], ["player_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("conversations", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_conversations_game_id"), ["game_id"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_conversations_player_profile_id"), ["player_profile_id"], unique=False
        )

    op.create_table(
        "chat_messages",
        sa.Column("conversation_id", sa.String(length=32), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("tool_calls", sa.JSON(), nullable=True),
        sa.Column("tool_call_id", sa.String(length=80), nullable=True),
        sa.Column("tool_name", sa.String(length=80), nullable=True),
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("chat_messages", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_chat_messages_conversation_id"), ["conversation_id"], unique=False
        )

    op.create_table(
        "companion_memories",
        sa.Column("player_profile_id", sa.String(length=32), nullable=False),
        sa.Column("game_id", sa.String(length=40), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("created_at", gcdb.UTCDateTime(), nullable=False),
        sa.Column("updated_at", gcdb.UTCDateTime(), nullable=False),
        sa.ForeignKeyConstraint(["player_profile_id"], ["player_profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("companion_memories", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_companion_memories_player_profile_id"),
            ["player_profile_id"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_table("companion_memories")
    op.drop_table("chat_messages")
    op.drop_table("conversations")
