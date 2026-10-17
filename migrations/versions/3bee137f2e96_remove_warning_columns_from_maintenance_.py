"""remove warning_km and warning_days from maintenance_operation_models

Revision ID: 3bee137f2e96
Revises: a7d1c40f5b2e
Create Date: 2026-10-11 10:35:24.973906

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3bee137f2e96'
down_revision: Union[str, Sequence[str], None] = 'a7d1c40f5b2e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Remove warning_km and warning_days columns from maintenance_operation_models
    op.drop_column('maintenance_operation_models', 'warning_km')
    op.drop_column('maintenance_operation_models', 'warning_days')


def downgrade() -> None:
    # Add back the columns if needed (nullable=True to not break existing data)
    op.add_column('maintenance_operation_models',
        sa.Column('warning_days', sa.Integer(), nullable=True))
    op.add_column('maintenance_operation_models',
        sa.Column('warning_km', sa.Numeric(10, 1), nullable=True))