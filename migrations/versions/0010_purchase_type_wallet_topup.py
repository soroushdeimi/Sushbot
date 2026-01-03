"""Add wallet_topup to purchasetype enum."""

from __future__ import annotations

from alembic import op

revision = "0010_purchase_type_wallet_topup"
down_revision = "0009_affiliate_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Postgres enum needs explicit extension
    op.execute("ALTER TYPE purchasetype ADD VALUE IF NOT EXISTS 'wallet_topup';")


def downgrade() -> None:
    # Postgres enums cannot easily remove values; keep as-is.
    pass


