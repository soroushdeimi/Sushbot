"""Add product categories table and category_id to products.

Revision ID: 0019_add_product_categories
Revises: 0018_add_test_panel_to_products
Create Date: 2025-01-XX 12:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0019_add_product_categories'
down_revision: str | None = '0018_add_test_panel_to_products'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add product categories table and category_id to products."""
    # Create product_categories table
    op.create_table(
        'product_categories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('slug', sa.String(255), nullable=True, unique=True),
        sa.Column('sort_order', sa.Integer(), default=0, nullable=False),
        sa.Column('parent_id', sa.Integer(), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['parent_id'], ['product_categories.id'], ondelete='SET NULL'),
    )
    op.create_index('ix_product_categories_slug', 'product_categories', ['slug'], unique=True)
    op.create_index('ix_product_categories_parent_id', 'product_categories', ['parent_id'])
    op.create_index('ix_product_categories_is_active', 'product_categories', ['is_active'])

    # Add category_id to products table
    op.add_column(
        'products',
        sa.Column('category_id', sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        'fk_products_category_id',
        'products',
        'product_categories',
        ['category_id'],
        ['id'],
        ondelete='SET NULL'
    )
    op.create_index('ix_products_category_id', 'products', ['category_id'])


def downgrade() -> None:
    """Remove product categories."""
    op.drop_index('ix_products_category_id', table_name='products')
    op.drop_constraint('fk_products_category_id', 'products', type_='foreignkey')
    op.drop_column('products', 'category_id')
    op.drop_table('product_categories')

