"""Separate model-private maintenance operations from the general library.

Revision ID: 20261023_maintenance_model_scoped_operations
Revises: 20261022_missions_drivers
"""
from alembic import op
import sqlalchemy as sa


revision = "20261023_maintenance_model_scoped_operations"
down_revision = "20261022_missions_drivers"
branch_labels = None
depends_on = None


def _columns(table_name):
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _indexes(table_name):
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def _foreign_keys(table_name):
    return {fk.get("name") for fk in sa.inspect(op.get_bind()).get_foreign_keys(table_name)}


def _tables():
    return set(sa.inspect(op.get_bind()).get_table_names())


def _create_model_operations_table():
    # init_db/create_all may have materialized the current model before Alembic
    # reaches this revision. Reuse that complete table instead of failing with
    # "table already exists"; indexes are checked separately below.
    if "maintenance_model_operations" in _tables():
        return
    op.create_table(
        "maintenance_model_operations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("equipment_model_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.Column("interval_km", sa.Numeric(10, 1), nullable=True),
        sa.Column("interval_hours", sa.Numeric(10, 1), nullable=True),
        sa.Column("interval_days", sa.Integer(), nullable=True),
        sa.Column("warning_km", sa.Numeric(10, 1), nullable=True),
        sa.Column("warning_days", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(
            ["equipment_model_id"], ["equipment_models.id"],
            name="fk_maintenance_model_operations_equipment_model", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["group_id"], ["maintenance_operation_groups.id"],
            name="fk_maintenance_model_operations_group", ondelete="SET NULL",
        ),
        sa.CheckConstraint("interval_km IS NULL OR interval_km > 0", name="ck_maintenance_model_operation_interval_km_positive"),
        sa.CheckConstraint("interval_hours IS NULL OR interval_hours > 0", name="ck_maintenance_model_operation_interval_hours_positive"),
        sa.CheckConstraint("interval_days IS NULL OR interval_days > 0", name="ck_maintenance_model_operation_interval_days_positive"),
        sa.CheckConstraint("warning_km IS NULL OR warning_km >= 0", name="ck_maintenance_model_operation_warning_km_nonnegative"),
        sa.CheckConstraint("warning_days IS NULL OR warning_days >= 0", name="ck_maintenance_model_operation_warning_days_nonnegative"),
    )
    op.create_index("ix_maintenance_model_operations_equipment_model_id", "maintenance_model_operations", ["equipment_model_id"])
    op.create_index("ix_maintenance_model_operations_group_id", "maintenance_model_operations", ["group_id"])
    op.create_index("ix_maintenance_model_operations_is_active", "maintenance_model_operations", ["is_active"])
    op.create_index("ix_maintenance_model_operations_id", "maintenance_model_operations", ["id"])


def upgrade():
    _create_model_operations_table()

    # Keep the existing general-operation FK while allowing a plan row to use
    # exactly one of the two operation libraries.
    if "model_operation_id" not in _columns("maintenance_plan_operations"):
        with op.batch_alter_table("maintenance_plan_operations") as batch:
            batch.alter_column("operation_id", existing_type=sa.Integer(), nullable=True)
            batch.add_column(sa.Column("model_operation_id", sa.Integer(), nullable=True))
            batch.create_foreign_key(
                "fk_maintenance_plan_operations_model_operation",
                "maintenance_model_operations", ["model_operation_id"], ["id"], ondelete="RESTRICT",
            )
            batch.create_check_constraint(
                "ck_maintenance_plan_operation_one_source",
                "(operation_id IS NOT NULL AND model_operation_id IS NULL) OR "
                "(operation_id IS NULL AND model_operation_id IS NOT NULL)",
            )
            batch.create_unique_constraint("uq_maintenance_plan_model_operation", ["plan_id", "model_operation_id"])
    if "ix_maintenance_plan_operations_model_operation_id" not in _indexes("maintenance_plan_operations"):
        op.create_index("ix_maintenance_plan_operations_model_operation_id", "maintenance_plan_operations", ["model_operation_id"])

    if "model_operation_id" not in _columns("maintenance_records"):
        with op.batch_alter_table("maintenance_records") as batch:
            batch.add_column(sa.Column("model_operation_id", sa.Integer(), nullable=True))
            batch.create_foreign_key(
                "fk_maintenance_records_model_operation",
                "maintenance_model_operations", ["model_operation_id"], ["id"], ondelete="RESTRICT",
            )
            batch.create_check_constraint(
                "ck_maintenance_record_one_operation_source",
                "operation_id IS NULL OR model_operation_id IS NULL",
            )
    indexes = _indexes("maintenance_records")
    if "ix_maintenance_records_model_operation_id" not in indexes:
        op.create_index("ix_maintenance_records_model_operation_id", "maintenance_records", ["model_operation_id"])
    if "uq_maintenance_record_equipment_model_operation_date" not in indexes:
        op.create_index(
            "uq_maintenance_record_equipment_model_operation_date",
            "maintenance_records", ["equipment_id", "model_operation_id", "maintenance_date"], unique=True,
        )

    # The previous uncommitted implementation stored private rows in the
    # general table behind scope_model_id. Transfer those rows and every FK
    # reference before removing the temporary column.
    if "scope_model_id" in _columns("maintenance_operations"):
        rows = op.get_bind().execute(sa.text(
            "SELECT o.id, o.name, o.description, o.group_id, o.warning_km, o.warning_days, o.is_active, "
            "c.interval_km, c.interval_hours, c.interval_days "
            "FROM maintenance_operations o LEFT JOIN maintenance_operation_models c "
            "ON c.operation_id = o.id AND c.equipment_model_id = o.scope_model_id "
            "WHERE o.scope_model_id IS NOT NULL ORDER BY o.id"
        )).mappings().all()
        for row in rows:
            op.get_bind().execute(sa.text(
                "INSERT INTO maintenance_model_operations "
                "(id, equipment_model_id, name, description, group_id, interval_km, interval_hours, interval_days, warning_km, warning_days, is_active) "
                "SELECT :id, scope_model_id, :name, :description, :group_id, :interval_km, :interval_hours, :interval_days, :warning_km, :warning_days, :is_active "
                "FROM maintenance_operations WHERE id = :id"
            ), {**dict(row)})
            op.get_bind().execute(sa.text(
                "UPDATE maintenance_plan_operations SET model_operation_id=:id, operation_id=NULL WHERE operation_id=:id"
            ), {"id": row["id"]})
            op.get_bind().execute(sa.text(
                "UPDATE maintenance_records SET model_operation_id=:id, operation_id=NULL WHERE operation_id=:id"
            ), {"id": row["id"]})
            op.get_bind().execute(sa.text(
                "DELETE FROM maintenance_operation_models WHERE operation_id=:id"
            ), {"id": row["id"]})
            op.get_bind().execute(sa.text("DELETE FROM maintenance_operations WHERE id=:id"), {"id": row["id"]})

        indexes = _indexes("maintenance_operations")
        foreign_keys = _foreign_keys("maintenance_operations")
        with op.batch_alter_table("maintenance_operations") as batch:
            if "ix_maintenance_operations_scope_model_id" in indexes:
                batch.drop_index("ix_maintenance_operations_scope_model_id")
            if "fk_maintenance_operations_scope_model" in foreign_keys:
                batch.drop_constraint("fk_maintenance_operations_scope_model", type_="foreignkey")
            batch.drop_column("scope_model_id")


def downgrade():
    # Restore the transitional schema only when IDs can be reinserted safely.
    if "scope_model_id" not in _columns("maintenance_operations"):
        with op.batch_alter_table("maintenance_operations") as batch:
            batch.add_column(sa.Column("scope_model_id", sa.Integer(), nullable=True))
            batch.create_foreign_key(
                "fk_maintenance_operations_scope_model", "equipment_models",
                ["scope_model_id"], ["id"], ondelete="RESTRICT",
            )
    if "ix_maintenance_operations_scope_model_id" not in _indexes("maintenance_operations"):
        op.create_index("ix_maintenance_operations_scope_model_id", "maintenance_operations", ["scope_model_id"])

    model_rows = op.get_bind().execute(sa.text("SELECT * FROM maintenance_model_operations ORDER BY id")).mappings().all()
    for row in model_rows:
        exists = op.get_bind().execute(sa.text("SELECT 1 FROM maintenance_operations WHERE id=:id"), {"id": row["id"]}).first()
        if exists:
            raise RuntimeError(f"Cannot downgrade: maintenance operation id {row['id']} now exists in the general library.")
        op.get_bind().execute(sa.text(
            "INSERT INTO maintenance_operations "
            "(id, name, description, group_id, interval_km, interval_hours, interval_days, warning_km, warning_days, is_active, scope_model_id) "
            "VALUES (:id, :name, :description, :group_id, :interval_km, :interval_hours, :interval_days, :warning_km, :warning_days, :is_active, :equipment_model_id)"
        ), dict(row))
        op.get_bind().execute(sa.text(
            "INSERT INTO maintenance_operation_models (operation_id, equipment_model_id, condition_source, interval_km, interval_hours, interval_days, is_active) "
            "VALUES (:id, :equipment_model_id, 'model', :interval_km, :interval_hours, :interval_days, :is_active)"
        ), dict(row))
        op.get_bind().execute(sa.text(
            "UPDATE maintenance_plan_operations SET operation_id=:id, model_operation_id=NULL WHERE model_operation_id=:id"
        ), {"id": row["id"]})
        op.get_bind().execute(sa.text(
            "UPDATE maintenance_records SET operation_id=:id, model_operation_id=NULL WHERE model_operation_id=:id"
        ), {"id": row["id"]})

    op.drop_index("uq_maintenance_record_equipment_model_operation_date", table_name="maintenance_records")
    op.drop_index("ix_maintenance_records_model_operation_id", table_name="maintenance_records")
    with op.batch_alter_table("maintenance_records") as batch:
        batch.drop_constraint("ck_maintenance_record_one_operation_source", type_="check")
        batch.drop_constraint("fk_maintenance_records_model_operation", type_="foreignkey")
        batch.drop_column("model_operation_id")
    if "ix_maintenance_plan_operations_model_operation_id" in _indexes("maintenance_plan_operations"):
        op.drop_index("ix_maintenance_plan_operations_model_operation_id", table_name="maintenance_plan_operations")
    with op.batch_alter_table("maintenance_plan_operations") as batch:
        batch.drop_constraint("uq_maintenance_plan_model_operation", type_="unique")
        batch.drop_constraint("ck_maintenance_plan_operation_one_source", type_="check")
        batch.drop_constraint("fk_maintenance_plan_operations_model_operation", type_="foreignkey")
        batch.drop_column("model_operation_id")
        batch.alter_column("operation_id", existing_type=sa.Integer(), nullable=False)
    op.drop_index("ix_maintenance_model_operations_id", table_name="maintenance_model_operations")
    op.drop_index("ix_maintenance_model_operations_is_active", table_name="maintenance_model_operations")
    op.drop_index("ix_maintenance_model_operations_group_id", table_name="maintenance_model_operations")
    op.drop_index("ix_maintenance_model_operations_equipment_model_id", table_name="maintenance_model_operations")
    op.drop_table("maintenance_model_operations")
