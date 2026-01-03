"""Payments idempotency: unique (gateway, gateway_transaction_id) when txid is present."""

from __future__ import annotations

from alembic import op

revision = "0003_payments_idempotency"
down_revision = "0002_support_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Use partial unique index to allow multiple NULL txids
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_payments_gateway_txid_partial
        ON payments(gateway, gateway_transaction_id)
        WHERE gateway_transaction_id IS NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_payments_gateway_txid_partial;")



