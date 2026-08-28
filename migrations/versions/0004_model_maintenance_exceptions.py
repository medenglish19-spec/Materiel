"""add model-specific maintenance exceptions.

Revision ID: 0004_model_maintenance_exceptions
Revises: 0003_equipment_classification
"""

from alembic import op
import sqlalchemy as sa


revision = "0004_model_maintenance_exceptions"
down_revision = "0003_equipment_classification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table(
        "maintenance_rules",
        naming_convention={"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"},
    ) as batch_op:
        batch_op.add_column(sa.Column("equipment_model_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("parent_rule_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_maintenance_rules_equipment_model_id", ["equipment_model_id"], unique=False)
        batch_op.create_index("ix_maintenance_rules_parent_rule_id", ["parent_rule_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_maintenance_rules_equipment_model",
            "equipment_models",
            ["equipment_model_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_foreign_key(
            "fk_maintenance_rules_parent_rule",
            "maintenance_rules",
            ["parent_rule_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_unique_constraint(
            "uq_maintenance_rule_parent_model",
            ["parent_rule_id", "equipment_model_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table(
        "maintenance_rules",
        naming_convention={"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"},
    ) as batch_op:
        batch_op.drop_constraint("uq_maintenance_rule_parent_model", type_="unique")
        batch_op.drop_constraint("fk_maintenance_rules_parent_rule", type_="foreignkey")
        batch_op.drop_constraint("fk_maintenance_rules_equipment_model", type_="foreignkey")
        batch_op.drop_index("ix_maintenance_rules_parent_rule_id")
        batch_op.drop_index("ix_maintenance_rules_equipment_model_id")
        batch_op.drop_column("parent_rule_id")
        batch_op.drop_column("equipment_model_id")
