"""Add WALLET_TOPUP to purchasetype enum (revision id must fit alembic_version)."""

from __future__ import annotations

from alembic import op

revision = "0011_purchasetype_wallettopup"
down_revision = "0010_purchase_type_wallet_topup"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE purchasetype ADD VALUE IF NOT EXISTS 'WALLET_TOPUP';")


def downgrade() -> None:
    pass
