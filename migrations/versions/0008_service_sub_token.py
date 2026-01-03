"""Add services.sub_token for subscription links."""

from __future__ import annotations

from alembic import op

revision = "0008_service_sub_token"
down_revision = "0007_wallet_transactions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE services ADD COLUMN IF NOT EXISTS sub_token VARCHAR(128) NULL;")
    # unique index for non-null tokens
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_services_sub_token_partial
        ON services(sub_token)
        WHERE sub_token IS NOT NULL;
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_services_sub_token_partial;")
    op.execute("ALTER TABLE services DROP COLUMN IF EXISTS sub_token;")
