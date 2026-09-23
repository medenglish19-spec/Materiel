"""link local equipment types to a technical library type

Revision ID: a1e6c8f4d2b7
Revises: 9c4d7e2a1b6f
"""

from alembic import op
import sqlalchemy as sa

revision = "a1e6c8f4d2b7"
down_revision = "9c4d7e2a1b6f"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    cols = {r[1] for r in bind.execute(sa.text("PRAGMA table_info(equipment_types)"))}
    if "technical_library_type_id" not in cols:
        bind.execute(sa.text(
            "ALTER TABLE equipment_types ADD COLUMN technical_library_type_id INTEGER "
            "REFERENCES equipment_types(id) ON DELETE SET NULL"
        ))
    bind.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS ix_equipment_types_technical_library_type_id "
        "ON equipment_types(technical_library_type_id)"
    ))

    # Existing local types with the same name as a system library type inherit
    # that library type automatically. Other local types keep their existing
    # category source and can be mapped explicitly from the UI.
    bind.execute(sa.text("""
        UPDATE equipment_types
        SET technical_library_type_id = (
            SELECT lib.id
            FROM equipment_types AS lib
            JOIN equipment_categories AS lc ON lc.id = lib.category_id
            WHERE lib.name = equipment_types.name
              AND lc.is_system = 1
              AND lib.id <> equipment_types.id
            LIMIT 1
        )
        WHERE technical_library_type_id IS NULL
          AND EXISTS (
            SELECT 1
            FROM equipment_types AS lib
            JOIN equipment_categories AS lc ON lc.id = lib.category_id
            WHERE lib.name = equipment_types.name
              AND lc.is_system = 1
              AND lib.id <> equipment_types.id
        )
    """))


def downgrade():
    bind = op.get_bind()
    # Keep the column on SQLite downgrade to avoid a destructive table rebuild.
