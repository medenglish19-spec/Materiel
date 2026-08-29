"""add model-specific maintenance exceptions.

Revision ID: 0004_model_maintenance_exceptions
Revises: 0003_equipment_classification
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "0004_model_maintenance_exceptions"
down_revision = "0003_equipment_classification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "maintenance_rules" not in inspector.get_table_names():
        return

    columns = {c["name"] for c in inspector.get_columns("maintenance_rules")}
    indexes = {c["name"] for c in inspector.get_indexes("maintenance_rules")}
    fks = {c["name"] for c in inspector.get_foreign_keys("maintenance_rules")}
    uniques = {c["name"] for c in inspector.get_unique_constraints("maintenance_rules")}

    with op.batch_alter_table(
        "maintenance_rules",
        naming_convention={"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"},
    ) as batch_op:
        if "equipment_model_id" not in columns:
            batch_op.add_column(sa.Column("equipment_model_id", sa.Integer(), nullable=True))
        if "parent_rule_id" not in columns:
            batch_op.add_column(sa.Column("parent_rule_id", sa.Integer(), nullable=True))
        if "ix_maintenance_rules_equipment_model_id" not in indexes:
            batch_op.create_index("ix_maintenance_rules_equipment_model_id", ["equipment_model_id"], unique=False)
        if "ix_maintenance_rules_parent_rule_id" not in indexes:
            batch_op.create_index("ix_maintenance_rules_parent_rule_id", ["parent_rule_id"], unique=False)
        if "fk_maintenance_rules_equipment_model" not in fks:
            batch_op.create_foreign_key(
                "fk_maintenance_rules_equipment_model",
                "equipment_models",
                ["equipment_model_id"],
                ["id"],
                ondelete="CASCADE",
            )
        if "fk_maintenance_rules_parent_rule" not in fks:
            batch_op.create_foreign_key(
                "fk_maintenance_rules_parent_rule",
                "maintenance_rules",
                ["parent_rule_id"],
                ["id"],
                ondelete="CASCADE",
            )
        if "uq_maintenance_rule_parent_model" not in uniques:
            batch_op.create_unique_constraint(
                "uq_maintenance_rule_parent_model",
                ["parent_rule_id", "equipment_model_id"],
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "maintenance_rules" not in inspector.get_table_names():
        return
    columns = {c["name"] for c in inspector.get_columns("maintenance_rules")}
    indexes = {c["name"] for c in inspector.get_indexes("maintenance_rules")}
    fks = {c["name"] for c in inspector.get_foreign_keys("maintenance_rules")}
    uniques = {c["name"] for c in inspector.get_unique_constraints("maintenance_rules")}

    with op.batch_alter_table(
        "maintenance_rules",
        naming_convention={"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"},
    ) as batch_op:
        if "uq_maintenance_rule_parent_model" in uniques:
            batch_op.drop_constraint("uq_maintenance_rule_parent_model", type_="unique")
        if "fk_maintenance_rules_parent_rule" in fks:
            batch_op.drop_constraint("fk_maintenance_rules_parent_rule", type_="foreignkey")
        if "fk_maintenance_rules_equipment_model" in fks:
            batch_op.drop_constraint("fk_maintenance_rules_equipment_model", type_="foreignkey")
        if "ix_maintenance_rules_parent_rule_id" in indexes:
            batch_op.drop_index("ix_maintenance_rules_parent_rule_id")
        if "ix_maintenance_rules_equipment_model_id" in indexes:
            batch_op.drop_index("ix_maintenance_rules_equipment_model_id")
        if "parent_rule_id" in columns:
            batch_op.drop_column("parent_rule_id")
        if "equipment_model_id" in columns:
            batch_op.drop_column("equipment_model_id")
