"""move theoretical quantity from equipment models to equipment types

revision: 0014
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_type_theoretical_quantity"
down_revision = "0013_batteries"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    type_columns = {c["name"] for c in inspector.get_columns("equipment_types")}

    if "theoretical_quantity" not in type_columns:
        op.add_column(
            "equipment_types",
            sa.Column("theoretical_quantity", sa.Integer(), nullable=False, server_default="0"),
        )

    # Preserve the existing configured totals when moving the setting from
    # individual models to the equipment type. A type-level quantity is the
    # total theoretical quantity for that type, so existing model quantities
    # are summed per type.
    op.execute(
        sa.text(
            """
            UPDATE equipment_types
            SET theoretical_quantity = COALESCE(
                (
                    SELECT SUM(em.theoretical_quantity)
                    FROM equipment_models em
                    WHERE em.equipment_type_id = equipment_types.id
                ),
                0
            )
            """
        )
    )

    inspector = sa.inspect(bind)
    model_columns = {c["name"] for c in inspector.get_columns("equipment_models")}
    if "theoretical_quantity" in model_columns:
        with op.batch_alter_table("equipment_models") as batch_op:
            batch_op.drop_column("theoretical_quantity")


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    model_columns = {c["name"] for c in inspector.get_columns("equipment_models")}

    if "theoretical_quantity" not in model_columns:
        op.add_column(
            "equipment_models",
            sa.Column("theoretical_quantity", sa.Integer(), nullable=False, server_default="0"),
        )

    # On downgrade, keep the type total available without inventing a model
    # allocation. The first model of each type receives the type total.
    op.execute(
        sa.text(
            """
            UPDATE equipment_models
            SET theoretical_quantity = COALESCE(
                (
                    SELECT et.theoretical_quantity
                    FROM equipment_types et
                    WHERE et.id = equipment_models.equipment_type_id
                ),
                0
            )
            WHERE equipment_models.id IN (
                SELECT MIN(em2.id)
                FROM equipment_models em2
                GROUP BY em2.equipment_type_id
            )
            """
        )
    )

    inspector = sa.inspect(bind)
    type_columns = {c["name"] for c in inspector.get_columns("equipment_types")}
    if "theoretical_quantity" in type_columns:
        with op.batch_alter_table("equipment_types") as batch_op:
            batch_op.drop_column("theoretical_quantity")
