"""Add type field to panels table

Revision ID: 0015_add_panel_type
Revises: 0014_add_quantity_to_purchases
Create Date: 2025-01-01 12:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0015_add_panel_type"
down_revision: str | None = "0014_add_quantity_to_purchases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add type column to panels table."""
    op.add_column("panels", sa.Column("type", sa.String(length=50), nullable=True))


def downgrade() -> None:
    """Remove type column from panels table."""
    op.drop_column("panels", "type")
