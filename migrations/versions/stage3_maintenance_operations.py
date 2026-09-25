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


def _fk_names(bind, table):
    return {fk.get("name") for fk in inspect(bind).get_foreign_keys(table)}


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
            sa.CheckConstraint("interval_km IS NOT NULL OR interval_hours IS NOT NULL OR interval_days IS NOT NULL", name="ck_maintenance_operation_has_interval"),
            sa.CheckConstraint("interval_km IS NULL OR interval_km > 0", name="ck_maintenance_operation_interval_km_positive"),
            sa.CheckConstraint("interval_hours IS NULL OR interval_hours > 0", name="ck_maintenance_operation_interval_hours_positive"),
            sa.CheckConstraint("interval_days IS NULL OR interval_days > 0", name="ck_maintenance_operation_interval_days_positive"),
            sa.CheckConstraint("warning_km IS NULL OR warning_km >= 0", name="ck_maintenance_operation_warning_km_nonnegative"),
            sa.CheckConstraint("warning_days IS NULL OR warning_days >= 0", name="ck_maintenance_operation_warning_days_nonnegative"),
            sa.ForeignKeyConstraint(["group_id"], ["maintenance_operation_groups.id"], name="fk_maintenance_operations_group", ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["old_rule_id"], ["maintenance_rules.id"], name="fk_maintenance_operations_old_rule", ondelete="RESTRICT"),
            sa.UniqueConstraint("old_rule_id", name="uq_maintenance_operation_old_rule"),
        )
        op.create_index("ix_maintenance_operations_group_id", "maintenance_operations", ["group_id"], unique=False)
        op.create_index("ix_maintenance_operations_old_rule_id", "maintenance_operations", ["old_rule_id"], unique=True)

    meta = sa.MetaData()
    rules = sa.Table("maintenance_rules", meta, autoload_with=bind)
    operations = sa.Table("maintenance_operations", meta, autoload_with=bind)
    audit = sa.Table("maintenance_operation_merge_audit", meta, autoload_with=bind)

    rows = bind.execute(sa.select(rules)).mappings().all()
    existing = bind.execute(sa.select(operations.c.id, operations.c.old_rule_id)).mappings().all()
    mapped_rules = {r["old_rule_id"] for r in existing if r["old_rule_id"] is not None}

    signatures = {}
    for row in rows:
        key = (row["name"], row["interval_km"], row["interval_hours"], row["interval_days"], row["warning_km"], row["warning_days"])
        signatures.setdefault(key, []).append(row)

    # Stage 3-a: exact technical signature audit. Existing production data has
    # zero maintenance rules, so this audit is empty and has no merge conflict.
    for key, group in signatures.items():
        operation_id = None
        eligible = [r for r in group if r["id"] not in mapped_rules]
        if eligible:
            source = eligible[0]
            operation_id = bind.execute(
                sa.insert(operations).values(
                    name=source["name"], interval_km=source["interval_km"],
                    interval_hours=source["interval_hours"], interval_days=source["interval_days"],
                    warning_km=source["warning_km"], warning_days=source["warning_days"],
                    is_active=bool(source["is_active"]), description=source["description"],
                    old_rule_id=source["id"],
                )
            ).inserted_primary_key[0]
            for duplicate in eligible[1:]:
                bind.execute(sa.insert(audit).values(
                    source_rule_id=duplicate["id"],
                    signature_key="|".join("" if v is None else str(v) for v in key),
                    operation_id=operation_id,
                    note="merged identical technical signature",
                ))
        for source in group:
            if source["id"] in mapped_rules:
                operation_id = bind.execute(
                    sa.select(operations.c.id).where(operations.c.old_rule_id == source["id"])
                ).scalar_one_or_none()
            if operation_id is not None and not bind.execute(
                sa.select(audit.c.id).where(audit.c.source_rule_id == source["id"]).limit(1)
            ).first():
                bind.execute(sa.insert(audit).values(
                    source_rule_id=source["id"],
                    signature_key="|".join("" if v is None else str(v) for v in key),
                    operation_id=operation_id,
                    note="source rule mapped to reusable operation",
                ))

    # Switch maintenance_records.operation_id from legacy rule IDs to operation IDs.
    tables = _tables(bind)
    if "maintenance_records" in tables:
        records = sa.Table("maintenance_records", meta, autoload_with=bind)
        if "operation_id" in {c["name"] for c in inspect(bind).get_columns("maintenance_records")}:
            for rec in bind.execute(sa.select(records.c.id, records.c.rule_id, records.c.operation_id)).mappings():
                if rec["operation_id"] is not None:
                    mapped = bind.execute(sa.select(operations.c.id).where(operations.c.old_rule_id == rec["rule_id"])).scalar_one_or_none()
                    if mapped is None:
                        mapped = bind.execute(sa.select(audit.c.operation_id).where(audit.c.source_rule_id == rec["rule_id"]).limit(1)).scalar_one_or_none()
                    if mapped is not None:
                        bind.execute(sa.update(records).where(records.c.id == rec["id"]).values(operation_id=mapped))
            fks = _fk_names(bind, "maintenance_records")
            with op.batch_alter_table("maintenance_records", naming_convention=_NAMING) as batch:
                if "fk_maintenance_records_operation" in fks:
                    batch.drop_constraint("fk_maintenance_records_operation", type_="foreignkey")
                batch.create_foreign_key("fk_maintenance_records_operation", "maintenance_operations", ["operation_id"], ["id"], ondelete="RESTRICT")

    # Create one default plan per model with active rules and attach the reusable operation.
    tables = _tables(bind)
    if "maintenance_plans" in tables and "maintenance_plan_operations" in tables:
        plans = sa.Table("maintenance_plans", meta, autoload_with=bind)
        plan_ops = sa.Table("maintenance_plan_operations", meta, autoload_with=bind)
        model_ids = bind.execute(
            sa.select(rules.c.equipment_model_id).where(rules.c.equipment_model_id.is_not(None), rules.c.is_active == True).distinct()
        ).scalars().all()
        for model_id in model_ids:
            plan_id = bind.execute(sa.select(plans.c.id).where(plans.c.equipment_model_id == model_id).limit(1)).scalar_one_or_none()
            if plan_id is None:
                plan_id = bind.execute(sa.insert(plans).values(
                    equipment_model_id=model_id,
                    name="خطة الصيانة الافتراضية",
                    is_active=True,
                    description="خطة أنشأتها عملية تحويل الصيانة القديمة؛ يمكن تعديلها لاحقًا.",
                )).inserted_primary_key[0]
            active_rules = bind.execute(sa.select(rules).where(rules.c.equipment_model_id == model_id, rules.c.is_active == True)).mappings().all()
            for rule in active_rules:
                operation_id = bind.execute(sa.select(operations.c.id).where(operations.c.old_rule_id == rule["id"])).scalar_one_or_none()
                if operation_id is None:
                    operation_id = bind.execute(sa.select(audit.c.operation_id).where(audit.c.source_rule_id == rule["id"]).limit(1)).scalar_one_or_none()
                if operation_id is None:
                    continue
                exists = bind.execute(sa.select(plan_ops.c.id).where(plan_ops.c.plan_id == plan_id, plan_ops.c.operation_id == operation_id)).scalar_one_or_none()
                if exists is None:
                    bind.execute(sa.insert(plan_ops).values(plan_id=plan_id, operation_id=operation_id, sort_order=0))

        fks = _fk_names(bind, "maintenance_plan_operations")
        with op.batch_alter_table("maintenance_plan_operations", naming_convention=_NAMING) as batch:
            if "fk_maintenance_plan_operations_operation" in fks:
                batch.drop_constraint("fk_maintenance_plan_operations_operation", type_="foreignkey")
            batch.create_foreign_key("fk_maintenance_plan_operations_operation", "maintenance_operations", ["operation_id"], ["id"], ondelete="RESTRICT")


def downgrade() -> None:
    bind = op.get_bind()
    tables = _tables(bind)
    if "maintenance_operations" not in tables:
        return
    meta = sa.MetaData()
    operations = sa.Table("maintenance_operations", meta, autoload_with=bind)
    audit = sa.Table("maintenance_operation_merge_audit", meta, autoload_with=bind) if "maintenance_operation_merge_audit" in tables else None

    if "maintenance_plan_operations" in tables:
        plan_ops = sa.Table("maintenance_plan_operations", meta, autoload_with=bind)
        for row in bind.execute(sa.select(plan_ops.c.id, plan_ops.c.operation_id)).mappings().all():
            old_rule = bind.execute(sa.select(operations.c.old_rule_id).where(operations.c.id == row["operation_id"])).scalar_one_or_none()
            if old_rule is None and audit is not None:
                old_rule = bind.execute(sa.select(audit.c.source_rule_id).where(audit.c.operation_id == row["operation_id"]).limit(1)).scalar_one_or_none()
            if old_rule is None:
                bind.execute(sa.delete(plan_ops).where(plan_ops.c.id == row["id"]))
            else:
                bind.execute(sa.update(plan_ops).where(plan_ops.c.id == row["id"]).values(operation_id=old_rule))
        fks = _fk_names(bind, "maintenance_plan_operations")
        with op.batch_alter_table("maintenance_plan_operations", naming_convention=_NAMING) as batch:
            if "fk_maintenance_plan_operations_operation" in fks:
                batch.drop_constraint("fk_maintenance_plan_operations_operation", type_="foreignkey")
            batch.create_foreign_key("fk_maintenance_plan_operations_operation", "maintenance_rules", ["operation_id"], ["id"], ondelete="RESTRICT")

    if "maintenance_records" in tables:
        records = sa.Table("maintenance_records", meta, autoload_with=bind)
        for row in bind.execute(sa.select(records.c.id, records.c.operation_id)).mappings().all():
            old_rule = bind.execute(sa.select(operations.c.old_rule_id).where(operations.c.id == row["operation_id"])).scalar_one_or_none()
            if old_rule is None and audit is not None:
                old_rule = bind.execute(sa.select(audit.c.source_rule_id).where(audit.c.operation_id == row["operation_id"]).limit(1)).scalar_one_or_none()
            bind.execute(sa.update(records).where(records.c.id == row["id"]).values(operation_id=old_rule))
        fks = _fk_names(bind, "maintenance_records")
        with op.batch_alter_table("maintenance_records", naming_convention=_NAMING) as batch:
            if "fk_maintenance_records_operation" in fks:
                batch.drop_constraint("fk_maintenance_records_operation", type_="foreignkey")
            batch.create_foreign_key("fk_maintenance_records_operation", "maintenance_rules", ["operation_id"], ["id"], ondelete="RESTRICT")

    if "maintenance_operations" in _tables(bind):
        op.drop_table("maintenance_operations")
    if "maintenance_operation_merge_audit" in _tables(bind):
        op.drop_table("maintenance_operation_merge_audit")
