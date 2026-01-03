"""Add users.password_hash for admin web panel login."""

from __future__ import annotations

from alembic import op

revision = "0005_user_password_hash"
down_revision = "0004_service_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(255) NULL;")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS password_hash;")
