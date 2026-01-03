"""Add allowed_protocols field to products table.

Revision ID: 0020_add_allowed_protocols
Revises: 0019_add_product_categories
Create Date: 2026-01-03 12:00:00.000000

This migration adds support for multi-protocol products, allowing
users to select their preferred VPN protocol (VLESS, VMESS, Trojan, etc.)
before purchasing a product.

Backward Compatibility:
- If allowed_protocols is NULL, the system falls back to the existing
  protocol field, maintaining full backward compatibility with existing products.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0020_add_allowed_protocols"
down_revision: str | None = "0019_add_product_categories"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add allowed_protocols column to products table.

    The allowed_protocols column stores a JSON array of protocol strings.
    Example: '["vless", "vmess", "trojan"]'

    If NULL, the product only supports the single protocol defined in
    the existing 'protocol' column.
    """
    op.add_column(
        "products",
        sa.Column(
            "allowed_protocols",
            sa.Text(),
            nullable=True,
            comment="JSON array of allowed protocols. NULL means single protocol from 'protocol' field.",
        ),
    )


def downgrade() -> None:
    """Remove allowed_protocols column from products table."""
    op.drop_column("products", "allowed_protocols")
