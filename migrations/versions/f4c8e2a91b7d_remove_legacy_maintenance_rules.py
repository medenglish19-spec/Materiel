"""Remove obsolete MaintenanceRule compatibility layer.

The maintenance subsystem is now operation-first. This migration is intentionally
destructive for the obsolete rule layer because the deployment contains no legacy
maintenance data that must be preserved.
"""
from alembic import op
import sqlalchemy as sa

revision = "f4c8e2a91b7d"
down_revision = "stage8_remove_plan_operation_overrides"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # This table was part of an older compatibility design but is not present
    # in the migration chain used by this deployment. Remove it only when it
    # actually exists so the final Operation-first cleanup remains idempotent.
    if "maintenance_operation_rule_map" in inspector.get_table_names():
        op.drop_table("maintenance_operation_rule_map")

    tables = set(inspector.get_table_names())

    if "maintenance_operations" in tables:
        # SQLite/Alembic can leave this generated table behind after a failed
        # batch rebuild. It is never part of the application schema, so remove
        # only this exact Alembic temporary artifact before retrying.
        if "_alembic_tmp_maintenance_operations" in tables:
            op.execute(sa.text("DROP TABLE IF EXISTS _alembic_tmp_maintenance_operations"))
            inspector = sa.inspect(bind)
            tables = set(inspector.get_table_names())

        operation_columns = {c["name"] for c in inspector.get_columns("maintenance_operations")}
        operation_indexes = {i.get("name") for i in inspector.get_indexes("maintenance_operations")}

        # A previous failed SQLite batch rebuild can leave the legacy index
        # behind even when old_rule_id has already been removed. Drop that
        # stale index before entering batch_alter_table; otherwise Alembic
        # reflects it and attempts to recreate an index on a missing column.
        if "ix_maintenance_operations_old_rule_id" in operation_indexes:
            op.drop_index("ix_maintenance_operations_old_rule_id", table_name="maintenance_operations")

        if "old_rule_id" in operation_columns:
            with op.batch_alter_table("maintenance_operations", schema=None) as batch_op:
                batch_op.drop_column("old_rule_id")

    if "maintenance_records" in tables:
        record_columns = {c["name"] for c in inspector.get_columns("maintenance_records")}
        record_constraints = {c.get("name") for c in inspector.get_unique_constraints("maintenance_records")}
        record_indexes = {i.get("name") for i in inspector.get_indexes("maintenance_records")}

        # A failed SQLite batch rebuild may leave an index for rule_id behind
        # even when the column itself is already absent. Remove that stale
        # index before entering batch_alter_table.
        if "ix_maintenance_records_rule_id" in record_indexes:
            op.drop_index("ix_maintenance_records_rule_id", table_name="maintenance_records")

        if "rule_id" in record_columns or "uq_maintenance_record_equipment_rule_date" in record_constraints:
            with op.batch_alter_table("maintenance_records", schema=None) as batch_op:
                if "uq_maintenance_record_equipment_rule_date" in record_constraints:
                    batch_op.drop_constraint("uq_maintenance_record_equipment_rule_date", type_="unique")
                if "rule_id" in record_columns:
                    batch_op.drop_column("rule_id")

    if "maintenance_rules" in tables:
        op.drop_table("maintenance_rules")


def downgrade():
    op.create_table(
        "maintenance_rules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("equipment_type_id", sa.Integer(), nullable=False),
        sa.Column("equipment_model_id", sa.Integer(), nullable=True),
        sa.Column("parent_rule_id", sa.Integer(), nullable=True),
        sa.Column("interval_km", sa.Numeric(10, 1), nullable=True),
        sa.Column("interval_hours", sa.Numeric(10, 1), nullable=True),
        sa.Column("interval_days", sa.Integer(), nullable=True),
        sa.Column("warning_km", sa.Numeric(10, 1), nullable=True),
        sa.Column("warning_days", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["equipment_type_id"], ["equipment_types.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["equipment_model_id"], ["equipment_models.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_rule_id"], ["maintenance_rules.id"], ondelete="CASCADE"),
    )
    with op.batch_alter_table("maintenance_records", schema=None) as batch_op:
        batch_op.add_column(sa.Column("rule_id", sa.Integer(), nullable=True))
        batch_op.create_unique_constraint(
            "uq_maintenance_record_equipment_rule_date",
            ["equipment_id", "rule_id", "maintenance_date"],
        )
    with op.batch_alter_table("maintenance_operations", schema=None) as batch_op:
        batch_op.add_column(sa.Column("old_rule_id", sa.Integer(), nullable=True))
    op.create_table(
        "maintenance_operation_rule_map",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("old_rule_id", sa.Integer(), nullable=False),
        sa.Column("operation_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["old_rule_id"], ["maintenance_rules.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["operation_id"], ["maintenance_operations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("old_rule_id", name="uq_maintenance_operation_rule_map_old_rule"),
    )
