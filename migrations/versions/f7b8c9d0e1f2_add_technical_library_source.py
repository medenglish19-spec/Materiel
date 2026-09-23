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
    # SQLite can add this nullable FK column directly; avoid batch table rebuilds
    # during application startup, which can block on existing SQLite databases.
    op.add_column(
        "equipment_types",
        sa.Column(
            "technical_library_category_id",
            sa.Integer(),
            sa.ForeignKey(
                "equipment_categories.id",
                name="fk_equipment_type_technical_library_category",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_equipment_types_technical_library_category_id",
        "equipment_types",
        ["technical_library_category_id"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_equipment_types_technical_library_category_id", table_name="equipment_types")
    op.drop_column("equipment_types", "technical_library_category_id")
