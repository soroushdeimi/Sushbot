"""Add reserved_quantity to products for inventory reservations."""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0013_product_reserved_quantity"
down_revision = "0012_app_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS reserved_quantity INTEGER NOT NULL DEFAULT 0;")


def downgrade() -> None:
    op.execute("ALTER TABLE products DROP COLUMN IF EXISTS reserved_quantity;")


