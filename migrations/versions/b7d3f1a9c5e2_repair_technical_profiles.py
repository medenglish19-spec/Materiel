"""repair technical library profiles and map existing local types

Revision ID: b7d3f1a9c5e2
Revises: a1e6c8f4d2b7
"""

from alembic import op
import sqlalchemy as sa

revision = "b7d3f1a9c5e2"
down_revision = "a1e6c8f4d2b7"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()

    # Every system technical type is its own profile. The profile mappings
    # created by the previous migration remain the source of applicability.
    bind.execute(sa.text("""
        UPDATE equipment_types
        SET technical_library_type_id = (
            SELECT lib.id
            FROM equipment_types lib
            JOIN equipment_categories cat ON cat.id = lib.category_id
            WHERE cat.is_system = 1
              AND lower(trim(lib.name)) = lower(trim(equipment_types.name))
              AND lib.id <> equipment_types.id
            ORDER BY lib.id
            LIMIT 1
        )
        WHERE EXISTS (
            SELECT 1
            FROM equipment_types lib
            JOIN equipment_categories cat ON cat.id = lib.category_id
            WHERE cat.is_system = 1
              AND lower(trim(lib.name)) = lower(trim(equipment_types.name))
              AND lib.id <> equipment_types.id
        )
    """))

    # Keep the technical category in sync with the selected technical type.
    bind.execute(sa.text("""
        UPDATE equipment_types
        SET technical_library_category_id = (
            SELECT lib.category_id
            FROM equipment_types lib
            WHERE lib.id = equipment_types.technical_library_type_id
        )
        WHERE technical_library_type_id IS NOT NULL
    """))


def downgrade():
    pass
