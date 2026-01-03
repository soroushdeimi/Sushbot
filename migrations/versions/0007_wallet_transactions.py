"""Add wallet_transactions table."""

from __future__ import annotations

from alembic import op

revision = "0007_wallet_transactions"
down_revision = "0006_audit_logs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS wallet_transactions (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            tx_type VARCHAR(32) NOT NULL DEFAULT 'adjust',
            amount INTEGER NOT NULL,
            balance_after INTEGER NOT NULL,
            ref VARCHAR(128) NULL,
            note TEXT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wallet_transactions_user_id ON wallet_transactions(user_id);"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wallet_transactions_tx_type ON wallet_transactions(tx_type);"
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_wallet_transactions_ref ON wallet_transactions(ref);")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wallet_transactions_created_at ON wallet_transactions(created_at);"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS wallet_transactions CASCADE;")
