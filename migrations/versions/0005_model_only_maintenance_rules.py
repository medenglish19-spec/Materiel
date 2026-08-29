"""scope maintenance rules to equipment models.

Revision ID: 0005_model_only_maintenance_rules
Revises: 0004_model_maintenance_exceptions
"""

from alembic import op
import sqlalchemy as sa


revision = "0005_model_only_maintenance_rules"
down_revision = "0004_model_maintenance_exceptions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    meta = sa.MetaData()
    rules = sa.Table("maintenance_rules", meta, autoload_with=bind)
    models = sa.Table("equipment_models", meta, autoload_with=bind)

    # Convert the existing type-wide rules into model-scoped rules without
    # deleting historical rules/records. Existing model exceptions take
    # precedence for their model; the base rule is used for other models.
    base_rows = bind.execute(
        sa.select(rules).where(
            rules.c.parent_rule_id.is_(None),
            rules.c.equipment_model_id.is_(None),
        )
    ).mappings().all()
    model_rows = bind.execute(sa.select(models)).mappings().all()

    for base in base_rows:
        same_type_models = [
            model for model in model_rows
            if model["equipment_type_id"] == base["equipment_type_id"]
        ]
        exceptions = {
            row["equipment_model_id"]: row
            for row in bind.execute(
                sa.select(rules).where(rules.c.parent_rule_id == base["id"])
            ).mappings().all()
            if row["equipment_model_id"] is not None
        }
        for model in same_type_models:
            source = exceptions.get(model["id"], base)
            exists = bind.execute(
                sa.select(rules.c.id).where(
                    rules.c.equipment_type_id == model["equipment_type_id"],
                    rules.c.equipment_model_id == model["id"],
                    rules.c.parent_rule_id.is_(None),
                    rules.c.name == source["name"],
                )
            ).scalar_one_or_none()
            if exists is not None:
                continue

            values = {
                "name": source["name"],
                "equipment_type_id": model["equipment_type_id"],
                "equipment_model_id": model["id"],
                "parent_rule_id": None,
                "interval_km": source["interval_km"],
                "interval_hours": source["interval_hours"],
                "interval_days": source["interval_days"],
                "warning_km": source["warning_km"],
                "warning_days": source["warning_days"],
                "is_active": source["is_active"],
                "description": source["description"],
            }
            # Keep timestamp/audit columns only when they exist in this schema.
            for key in ("created_at", "updated_at", "created_by_id", "updated_by_id"):
                if key in rules.c and key in source:
                    values[key] = source[key]
            bind.execute(rules.insert().values(**values))

    # Old type-wide rules and their exception rows remain as historical data
    # but are no longer active. Existing maintenance_records still reference
    # them safely.
    bind.execute(
        rules.update()
        .where(
            sa.or_(
                rules.c.parent_rule_id.is_not(None),
                rules.c.equipment_model_id.is_(None),
            )
        )
        .values(is_active=False)
    )


def downgrade() -> None:
    # Deliberately leave cloned model rules intact. Removing them could destroy
    # user-maintained changes made after this migration.
    pass
