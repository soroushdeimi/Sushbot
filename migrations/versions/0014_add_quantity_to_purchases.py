"""Add quantity column to purchases table.

Revision ID: 0014_add_quantity
Revises: 0013_product_reserved_quantity
Create Date: 2025-12-26 08:36:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0014_add_quantity'
down_revision = '0013_product_reserved_quantity'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('purchases', sa.Column('quantity', sa.Integer(), nullable=False, server_default='1'))


def downgrade() -> None:
    op.drop_column('purchases', 'quantity')

