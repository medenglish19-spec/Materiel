"""Remove obsolete technical library source fields from equipment types.

Revision ID: e4f7a1c2b9d0
Revises: d9f4a7c1e2b3
"""

from alembic import op
import sqlalchemy as sa


revision = "e4f7a1c2b9d0"
down_revision = "d9f4a7c1e2b3"
branch_labels = None
depends_on = None

_NAMING = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}


def upgrade():
    op.execute("DROP INDEX IF EXISTS ix_equipment_types_technical_library_type_id")
    op.execute("DROP INDEX IF EXISTS ix_equipment_types_technical_library_category_id")

    with op.batch_alter_table("equipment_types", schema=None) as batch_op:
        batch_op.drop_column("technical_library_category_id")
        batch_op.drop_column("technical_library_type_id")


def downgrade():
    with op.batch_alter_table("equipment_types", schema=None, naming_convention=_NAMING) as batch_op:
        batch_op.add_column(
            sa.Column(
                "technical_library_category_id",
                sa.Integer(),
                nullable=True,
            )
        )
        batch_op.create_foreign_key(
            "fk_equipment_types_technical_library_category_id_equipment_categories",
            "equipment_categories",
            ["technical_library_category_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.add_column(
            sa.Column(
                "technical_library_type_id",
                sa.Integer(),
                nullable=True,
            )
        )
        batch_op.create_foreign_key(
            "fk_equipment_types_technical_library_type_id_equipment_types",
            "equipment_types",
            ["technical_library_type_id"],
            ["id"],
            ondelete="SET NULL",
        )
