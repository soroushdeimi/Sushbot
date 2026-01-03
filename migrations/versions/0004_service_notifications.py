"""Add notification timestamps to services."""

from __future__ import annotations

from alembic import op

revision = "0004_service_notifications"
down_revision = "0003_payments_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE services ADD COLUMN IF NOT EXISTS last_expiry_notified_at TIMESTAMPTZ NULL;")
    op.execute("ALTER TABLE services ADD COLUMN IF NOT EXISTS last_traffic_notified_at TIMESTAMPTZ NULL;")
    op.execute("CREATE INDEX IF NOT EXISTS ix_services_last_expiry_notified_at ON services(last_expiry_notified_at);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_services_last_traffic_notified_at ON services(last_traffic_notified_at);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_services_last_traffic_notified_at;")
    op.execute("DROP INDEX IF EXISTS ix_services_last_expiry_notified_at;")
    op.execute("ALTER TABLE services DROP COLUMN IF EXISTS last_traffic_notified_at;")
    op.execute("ALTER TABLE services DROP COLUMN IF EXISTS last_expiry_notified_at;")



