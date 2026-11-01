"""add freeze controls for equipment types and models

revision: 0014
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_freeze_equipment_master_data"
down_revision = "0013_batteries"
branch_labels = None
depends_on = None

_FOREIGN_KEY_NAMING_CONVENTION = {"fk": "fk_%(table_name)s_%(column_0_name)s"}


def upgrade():
    op.add_column("equipment_types", sa.Column("is_frozen", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("equipment_models", sa.Column("is_frozen", sa.Boolean(), nullable=False, server_default=sa.false()))
    for table_name in ("equipment_types", "equipment_models"):
        with op.batch_alter_table(
            table_name, naming_convention=_FOREIGN_KEY_NAMING_CONVENTION
        ) as batch_op:
            batch_op.alter_column(
                "is_frozen",
                existing_type=sa.Boolean(),
                existing_nullable=False,
                existing_server_default=sa.false(),
                server_default=None,
            )


def downgrade():
    for table_name in ("equipment_models", "equipment_types"):
        with op.batch_alter_table(
            table_name, naming_convention=_FOREIGN_KEY_NAMING_CONVENTION
        ) as batch_op:
            batch_op.drop_column("is_frozen")
