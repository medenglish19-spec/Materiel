"""add freeze controls for equipment types and models

revision: 0014
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_freeze_equipment_master_data"
down_revision = "0013_batteries"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("equipment_types", sa.Column("is_frozen", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("equipment_models", sa.Column("is_frozen", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.alter_column("equipment_types", "is_frozen", server_default=None)
    op.alter_column("equipment_models", "is_frozen", server_default=None)


def downgrade():
    op.drop_column("equipment_models", "is_frozen")
    op.drop_column("equipment_types", "is_frozen")
