"""Add encryption fields and update panel structure.

Revision ID: 0016_add_panel_encryption
Revises: 0015_add_panel_type
Create Date: 2025-01-01 12:30:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0016_add_panel_encryption"
down_revision: str | None = "0015_add_panel_type"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add encryption fields and update panel structure."""
    # Change api_key to Text (for encrypted data)
    op.alter_column(
        "panels", "api_key", existing_type=sa.String(255), type_=sa.Text(), existing_nullable=False
    )

    # Make node_id nullable with default 0 (for Marzban)
    op.alter_column(
        "panels", "node_id", existing_type=sa.Integer(), nullable=True, server_default="0"
    )

    # Add username and password fields (optional, for Marzban)
    op.add_column("panels", sa.Column("username", sa.String(length=255), nullable=True))
    op.add_column("panels", sa.Column("password", sa.Text(), nullable=True))

    # Add inbound_tag field for PasarGuard
    op.add_column(
        "panels",
        sa.Column("inbound_tag", sa.String(length=100), nullable=True, server_default="SUSH"),
    )


def downgrade() -> None:
    """Remove encryption fields."""
    op.drop_column("panels", "inbound_tag")
    op.drop_column("panels", "password")
    op.drop_column("panels", "username")
    op.alter_column(
        "panels", "node_id", existing_type=sa.Integer(), nullable=False, server_default=None
    )
    op.alter_column(
        "panels", "api_key", existing_type=sa.Text(), type_=sa.String(255), existing_nullable=False
    )
