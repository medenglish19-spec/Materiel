"""add technical library source to user equipment types

Revision ID: f7b8c9d0e1f2
Revises: f1a2b3c4d5e6
"""

from alembic import op
import sqlalchemy as sa

revision = "f7b8c9d0e1f2"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("equipment_types", schema=None) as batch_op:
        batch_op.add_column(sa.Column("technical_library_category_id", sa.Integer(), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_equipment_types_technical_library_category_id"),
            ["technical_library_category_id"],
            unique=False,
        )
        batch_op.create_foreign_key(
            "fk_equipment_type_technical_library_category",
            "equipment_categories",
            ["technical_library_category_id"],
            ["id"],
            ondelete="SET NULL",
        )


def downgrade():
    with op.batch_alter_table("equipment_types", schema=None) as batch_op:
        batch_op.drop_constraint("fk_equipment_type_technical_library_category", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_equipment_types_technical_library_category_id"))
        batch_op.drop_column("technical_library_category_id")
