"""Add test_panel_id to products table.

Revision ID: 0018_add_test_panel_to_products
Revises: 0017_add_reseller_tables
Create Date: 2025-01-XX 12:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0018_add_test_panel_to_products'
down_revision: str | None = '0017_add_reseller_tables'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add test_panel_id column to products table."""
    op.add_column(
        'products',
        sa.Column('test_panel_id', sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        'fk_products_test_panel_id',
        'products',
        'panels',
        ['test_panel_id'],
        ['id'],
        ondelete='SET NULL'
    )
    op.create_index('ix_products_test_panel_id', 'products', ['test_panel_id'])


def downgrade() -> None:
    """Remove test_panel_id column from products table."""
    op.drop_index('ix_products_test_panel_id', table_name='products')
    op.drop_constraint('fk_products_test_panel_id', 'products', type_='foreignkey')
    op.drop_column('products', 'test_panel_id')

