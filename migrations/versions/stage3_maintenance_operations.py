"""Convert model-specific maintenance rules into reusable maintenance operations.

Revision ID: stage3_maintenance_operations
Revises: stage2_maintenance_structure
"""

from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa


revision = "stage3_maintenance_operations"
down_revision = "stage2_maintenance_structure"
branch_labels = None
depends_on = None

_NAMING = {"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"}


def _tables(bind):
    return set(inspect(bind).get_table_names())


def upgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)
    if "maintenance_rules" not in tables:
        return

    if "maintenance_operation_merge_audit" not in tables:
        op.create_table(
            "maintenance_operation_merge_audit",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source_rule_id", sa.Integer(), nullable=False),
            sa.Column("signature_key", sa.String(500), nullable=False),
            sa.Column("operation_id", sa.Integer(), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(
                ["source_rule_id"], ["maintenance_rules.id"],
                name="fk_maintenance_operation_merge_audit_source_rule",
                ondelete="RESTRICT",
            ),
        )
        op.create_index(
            "ix_maintenance_operation_merge_audit_source_rule_id",
            "maintenance_operation_merge_audit",
            ["source_rule_id"], unique=False,
        )

    tables = _tables(bind)
    if "maintenance_operations" not in tables:
        op.create_table(
            "maintenance_operations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("interval_km", sa.Numeric(10, 1), nullable=True),
            sa.Column("interval_hours", sa.Numeric(10, 1), nullable=True),
            sa.Column("interval_days", sa.Integer(), nullable=True),
            sa.Column("warning_km", sa.Numeric(10, 1), nullable=True),
            sa.Column("warning_days", sa.Integer(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("group_id", sa.Integer(), nullable=True),
            sa.Column("old_rule_id", sa.Integer(), nullable=True),
            sa.CheckConstraint(
                "interval_km IS NOT NULL OR interval_hours IS NOT NULL OR interval_days IS NOT NULL",
                name="ck_maintenance_operation_has_interval",
            ),
            sa.CheckConstraint("interval_km IS NULL OR interval_km > 0", name="ck_maintenance_operation_interval_km_positive"),
            sa.CheckConstraint("interval_hours IS NULL OR interval_hours > 0", name="ck_maintenance_operation_interval_hours_positive"),
            sa.CheckConstraint("interval_days IS NULL OR interval_days > 0", name="ck_maintenance_operation_interval_days_positive"),
            sa.CheckConstraint("warning_km IS NULL OR warning_km >= 0", name="ck_maintenance_operation_warning_km_nonnegative"),
            sa.CheckConstraint("warning_days IS NULL OR warning_days >= 0", name="ck_maintenance_operation_warning_days_nonnegative"),
            sa.ForeignKeyConstraint(
                ["group_id"], ["maintenance_operation_groups.id"],
                name="fk_maintenance_operations_group", ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["old_rule_id"], ["maintenance_rules.id"],
                name="fk_maintenance_operations_old_rule", ondelete="RESTRICT",
            ),
            sa.UniqueConstraint("old_rule_id", name="uq_maintenance_operation_old_rule"),
        )
        op.create_index("ix_maintenance_operations_group_id", "maintenance_operations", ["group_id"], unique=False)
        op.create_index("ix_maintenance_operations_old_rule_id", "maintenance_operations", ["old_rule_id"], unique=True)

    meta = sa.MetaData()
    rules = sa.Table("maintenance_rules", meta, autoload_with=bind)
    operations = sa.Table("maintenance_operations", meta, autoload_with=bind)
    audit = sa.Table("maintenance_operation_merge_audit", meta, autoload_with=bind)

    existing_ops = bind.execute(sa.select(operations.c.id, operations.c.old_rule_id)).mappings().all()
    mapped_rules = {row["old_rule_id"] for row in existing_ops if row["old_rule_id"] is not None}
    rows = bind.execute(sa.select(rules)).mappings().all()

    # Stage 3-a audit: the merge key is exactly the agreed technical signature.
    # With the current production database there are zero rules, so this audit
    # is empty and no manual merge conflict exists.
    signatures = {}
    for row in rows:
        key_values = (
            row["name"], row["interval_km"], row["interval_hours"],
            row["interval_days"], row["warning_km"], row["warning_days"],
        )
        signature = "|".join("" if value is None else str(value) for value in key_values)
        signatures.setdefault(key_values, []).append(row)

    for key_values, group in signatures.items():
        operation_id = None
        eligible = [r for r in group if r["id"] not in mapped_rules]
        if eligible:
            source = eligible[0]
            operation_id = bind.execute(
                sa.insert(operations).values(
                    name=source["name"],
                    interval_km=source["interval_km"],
                    interval_hours=source["interval_hours"],
                    interval_days=source["interval_days"],
                    warning_km=source["warning_km"],
                    warning_days=source["warning_days"],
                    is_active=bool(source["is_active"]),
                    description=source["description"],
                    old_rule_id=source["id"],
                )
            ).inserted_primary_key[0]
            # The legacy rule remains preserved; additional identical rules
            # are recorded in the audit and linked to the same reusable operation.
            for duplicate in eligible[1:]:
                bind.execute(
                    sa.insert(audit).values(
                        source_rule_id=duplicate["id"],
                        signature_key=signature,
                        operation_id=operation_id,
                        note="merged identical technical signature",
                    )
                )
        for source in group:
            if source["id"] in mapped_rules:
                existing = bind.execute(
                    sa.select(operations.c.id).where(operations.c.old_rule_id == source["id"])
                ).scalar_one_or_none()
                operation_id = existing
            if operation_id is not None and source["id"] not in mapped_rules:
                bind.execute(
                    sa.insert(audit).values(
                        source_rule_id=source["id"],
                        signature_key=signature,
                        operation_id=operation_id,
                        note="source rule mapped to reusable operation",
                    )
                )

    # Populate Stage 2's operation_id using the permanent mapping. The column
    # still points to maintenance_rules at this moment, so it is safe to copy
    # the source rule id until the FK is switched to maintenance_operations.
    if "maintenance_records" in tables:
        records = sa.Table("maintenance_records", meta, autoload_with=bind)
        op_columns = {c["name"] for c in inspect(bind).get_columns("maintenance_records")}
        if "operation_id" in op_columns:
            bind.execute(
                sa.update(records)
                .where(records.c.operation_id.is_(None))
                .values(operation_id=records.c.rule_id)
            )

    # Create one default plan per model that has active model-specific rules.
    if "maintenance_plans" in tables and "maintenance_plan_operations" in tables and "equipment_models" in tables:
        plans = sa.Table("maintenance_plans", meta, autoload_with=bind)
        plan_ops = sa.Table("maintenance_plan_operations", meta, autoload_with=bind)
        models = sa.Table("equipment_models", meta, autoload_with=bind)
        model_ids = bind.execute(
            sa.select(rules.c.equipment_model_id)
            .where(rules.c.equipment_model_id.is_not(None), rules.c.is_active == True)
            .distinct()
        ).scalars().all()
        for model_id in model_ids:
            plan_id = bind.execute(
                sa.select(plans.c.id).where(plans.c.equipment_model_id == model_id).limit(1)
            ).scalar_one_or_none()
            if plan_id is None:
                plan_id = bind.execute(
                    sa.insert(plans).values(
                        equipment_model_id=model_id,
                        name="خطة الصيانة الافتراضية",
                        is_active=True,
                        description="خطة أنشأتها عملية تحويل الصيانة القديمة؛ يمكن تعديلها لاحقًا.",
                    )
                ).inserted_primary_key[0]
            active_rules = bind.execute(
                sa.select(rules).where(
                    rules.c.equipment_model_id == model_id,
                    rules.c.is_active == True,
                )
            ).mappings().all()
            for rule in active_rules:
                operation_id = bind.execute(
                    sa.select(operations.c.id).where(operations.c.old_rule_id == rule["id"])
                ).scalar_one_or_none()
                if operation_id is None:
                    # A duplicate source may be represented only in the audit.
                    operation_id = bind.execute(
                        sa.select(audit.c.operation_id).where(audit.c.source_rule_id == rule["id"]).limit(1)
                    ).scalar_one_or_none()
                if operation_id is None:
                    continue
                exists = bind.execute(
                    sa.select(plan_ops.c.id).where(
                        plan_ops.c.plan_id == plan_id,
                        plan_ops.c.operation_id == rule["id"],
                    )
                ).scalar_one_or_none()
                if exists is None:
                    bind.execute(
                        sa.insert(plan_ops).values(
                            plan_id=plan_id,
                            operation_id=rule["id"],
                            sort_order=0,
                        )
                    )


def downgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)
    if "maintenance_records" in tables:
        columns = {c["name"] for c in inspect(bind).get_columns("maintenance_records")}
        fks = {fk.get("name") for fk in inspect(bind).get_foreign_keys("maintenance_records")}
        if "operation_id" in columns:
            with op.batch_alter_table("maintenance_records", naming_convention=_NAMING) as batch:
                if "fk_maintenance_records_operation" in fks:
                    batch.drop_constraint("fk_maintenance_records_operation", type_="foreignkey")
                batch.create_foreign_key(
                    "fk_maintenance_records_operation",
                    "maintenance_rules", ["operation_id"], ["id"], ondelete="RESTRICT",
                )

    if "maintenance_operations" in tables:
        op.drop_table("maintenance_operations")
    if "maintenance_operation_merge_audit" in tables:
        op.drop_table("maintenance_operation_merge_audit")
