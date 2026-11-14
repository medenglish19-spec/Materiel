"""Persist the selected equipment model on driver records."""
from alembic import op
import sqlalchemy as sa


revision = "20261030_driver_model"
down_revision = "20261030_driver_reg"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("drivers") as batch_op:
        batch_op.add_column(sa.Column("equipment_model_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_drivers_equipment_model_id_equipment_models",
            "equipment_models",
            ["equipment_model_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_drivers_equipment_model_id", ["equipment_model_id"])

    op.execute(
        sa.text(
            "UPDATE drivers "
            "SET equipment_model_id = ("
            "SELECT equipment.equipment_model_id FROM equipment "
            "WHERE equipment.id = drivers.assigned_equipment_id"
            ") "
            "WHERE assigned_equipment_id IS NOT NULL"
        )
    )


def downgrade():
    with op.batch_alter_table("drivers") as batch_op:
        batch_op.drop_index("ix_drivers_equipment_model_id")
        batch_op.drop_constraint(
            "fk_drivers_equipment_model_id_equipment_models",
            type_="foreignkey",
        )
        batch_op.drop_column("equipment_model_id")
