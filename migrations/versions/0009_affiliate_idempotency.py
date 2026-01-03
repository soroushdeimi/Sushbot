"""Affiliate safety: FK users.referred_by_id + wallet ref idempotency."""

from __future__ import annotations

from alembic import op

revision = "0009_affiliate_idempotency"
down_revision = "0008_service_sub_token"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # users.referred_by_id foreign key (self-referential)
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name='users' AND column_name='referred_by_id'
            ) THEN
                ALTER TABLE users ADD COLUMN referred_by_id BIGINT NULL;
            END IF;
        END $$;
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_users_referred_by_id ON users(referred_by_id);")
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='fk_users_referred_by_id') THEN
                ALTER TABLE users
                ADD CONSTRAINT fk_users_referred_by_id
                FOREIGN KEY (referred_by_id)
                REFERENCES users(id)
                ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )

    # wallet_transactions.ref should be unique when present (idempotency keys)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_wallet_transactions_ref_not_null ON wallet_transactions(ref) WHERE ref IS NOT NULL;"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_wallet_transactions_ref_not_null;")
    op.execute("ALTER TABLE users DROP CONSTRAINT IF EXISTS fk_users_referred_by_id;")
    op.execute("DROP INDEX IF EXISTS ix_users_referred_by_id;")
