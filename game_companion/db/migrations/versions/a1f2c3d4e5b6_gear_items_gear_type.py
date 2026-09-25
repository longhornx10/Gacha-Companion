"""gear_items.gear_type (M21): gear families per adapter (disc/relic/ornament/cartridge...).

All existing rows are ZZZ Drive Discs, so the column lands NOT NULL with
server_default 'disc' — no backfill pass needed.

Revision ID: a1f2c3d4e5b6
Revises: 9d7ff9044b3e
Create Date: 2026-09-23

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "a1f2c3d4e5b6"
down_revision: str | None = "9d7ff9044b3e"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "gear_items",
        sa.Column("gear_type", sa.String(length=40), nullable=False, server_default="disc"),
    )
    op.create_index("ix_gear_items_gear_type", "gear_items", ["gear_type"])


def downgrade() -> None:
    op.drop_index("ix_gear_items_gear_type", table_name="gear_items")
    op.drop_column("gear_items", "gear_type")
