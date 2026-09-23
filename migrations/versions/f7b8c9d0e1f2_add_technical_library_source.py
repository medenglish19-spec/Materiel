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
    bind = op.get_bind()
    columns = {row[1] for row in bind.execute(sa.text("PRAGMA table_info(equipment_types)"))}
    if "technical_library_category_id" not in columns:
        bind.execute(sa.text(
            "ALTER TABLE equipment_types ADD COLUMN "
            "technical_library_category_id INTEGER "
            "REFERENCES equipment_categories(id) ON DELETE SET NULL"
        ))

    indexes = {row[1] for row in bind.execute(sa.text("PRAGMA index_list(equipment_types)"))}
    if "ix_equipment_types_technical_library_category_id" not in indexes:
        op.create_index(
            "ix_equipment_types_technical_library_category_id",
            "equipment_types",
            ["technical_library_category_id"],
            unique=False,
        )


def downgrade():
    bind = op.get_bind()
    indexes = {row[1] for row in bind.execute(sa.text("PRAGMA index_list(equipment_types)"))}
    if "ix_equipment_types_technical_library_category_id" in indexes:
        op.drop_index(
            "ix_equipment_types_technical_library_category_id",
            table_name="equipment_types",
        )
    # SQLite cannot reliably drop a column without rebuilding the table.
    # Keep the column on downgrade rather than risking data loss.
