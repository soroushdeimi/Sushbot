"""Add reseller pricing and quota tables.

Revision ID: 0017_add_reseller_tables
Revises: 0016_add_panel_encryption
Create Date: 2025-01-XX 12:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0017_add_reseller_tables'
down_revision: Union[str, None] = '0016_add_panel_encryption'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add reseller pricing and quota tables."""
    # Reseller Pricing Table
    op.create_table(
        'reseller_pricing',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('reseller_id', sa.BigInteger(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=False),
        sa.Column('discount_percent', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['reseller_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('reseller_id', 'product_id', name='uq_reseller_product'),
    )
    op.create_index('ix_reseller_pricing_reseller_id', 'reseller_pricing', ['reseller_id'])
    op.create_index('ix_reseller_pricing_product_id', 'reseller_pricing', ['product_id'])
    
    # Reseller Quota Table
    op.create_table(
        'reseller_quotas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('reseller_id', sa.BigInteger(), nullable=False),
        sa.Column('product_id', sa.Integer(), nullable=True),  # None = global quota
        sa.Column('monthly_limit', sa.Integer(), nullable=True),  # None = unlimited
        sa.Column('current_month_usage', sa.Integer(), default=0, nullable=False),
        sa.Column('reset_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['reseller_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['product_id'], ['products.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('reseller_id', 'product_id', name='uq_reseller_quota'),
    )
    op.create_index('ix_reseller_quotas_reseller_id', 'reseller_quotas', ['reseller_id'])
    op.create_index('ix_reseller_quotas_product_id', 'reseller_quotas', ['product_id'])


def downgrade() -> None:
    """Remove reseller tables."""
    op.drop_table('reseller_quotas')
    op.drop_table('reseller_pricing')

