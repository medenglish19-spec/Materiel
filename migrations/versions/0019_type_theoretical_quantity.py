"""move theoretical quantity from equipment models to equipment types

This migration is intentionally based on the real migration head (0018).
The earlier 0014_type_theoretical_quantity file was orphaned from the main
migration chain because 0014_fuel already used 0013_batteries as its parent.
"""
from alembic import op
import sqlalchemy as sa

revision = "0019_type_theoretical_quantity"
down_revision = "0018_tire_model_configuration_and_disposal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    type_columns = {column["name"] for column in inspector.get_columns("equipment_types")}
    if "theoretical_quantity" not in type_columns:
        op.add_column(
            "equipment_types",
            sa.Column("theoretical_quantity", sa.Integer(), nullable=False, server_default="0"),
        )

    model_columns = {column["name"] for column in inspector.get_columns("equipment_models")}
    if "theoretical_quantity" in model_columns:
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
        with op.batch_alter_table("equipment_models") as batch_op:
            batch_op.drop_column("theoretical_quantity")


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    model_columns = {column["name"] for column in inspector.get_columns("equipment_models")}
    if "theoretical_quantity" not in model_columns:
        op.add_column(
            "equipment_models",
            sa.Column("theoretical_quantity", sa.Integer(), nullable=False, server_default="0"),
        )

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

    type_columns = {column["name"] for column in inspector.get_columns("equipment_types")}
    if "theoretical_quantity" in type_columns:
        with op.batch_alter_table("equipment_types") as batch_op:
            batch_op.drop_column("theoretical_quantity")
