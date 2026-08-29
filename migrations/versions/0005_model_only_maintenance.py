"""make active maintenance schedules model-specific.

Existing type-level rules are preserved as inactive historical rules. For every
model under a legacy rule's type, a model-specific rule is created. Existing
maintenance records are reassigned to the matching model rule when possible.
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_model_only_maintenance"
down_revision = "0004_model_maintenance_exceptions"
branch_labels = None
depends_on = None


def _columns(bind, table):
    return {c["name"] for c in sa.inspect(bind).get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "maintenance_rules" not in inspector.get_table_names():
        return

    columns = _columns(bind, "maintenance_rules")
    with op.batch_alter_table(
        "maintenance_rules",
        naming_convention={
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
        },
    ) as batch:
        if "equipment_model_id" not in columns:
            batch.add_column(sa.Column("equipment_model_id", sa.Integer(), nullable=True))
            batch.create_index(
                "ix_maintenance_rules_equipment_model_id",
                ["equipment_model_id"],
                unique=False,
            )
        if "ck_maintenance_rule_active_requires_model" not in {
            c.get("name") for c in inspector.get_check_constraints("maintenance_rules")
        }:
            batch.create_check_constraint(
                "ck_maintenance_rule_active_requires_model",
                "equipment_model_id IS NOT NULL OR is_active = 0",
            )

    meta = sa.MetaData()
    rules = sa.Table("maintenance_rules", meta, autoload_with=bind)
    models = sa.Table("equipment_models", meta, autoload_with=bind)
    equipment = sa.Table("equipment", meta, autoload_with=bind)
    records = sa.Table("maintenance_records", meta, autoload_with=bind)

    legacy_rules = bind.execute(
        sa.select(rules).where(rules.c.equipment_model_id.is_(None))
    ).mappings().all()

    # Map every legacy rule to one new rule per model. Exceptions override the
    # base values for their target model, but remain separate historical rows.
    model_rules = {}
    for base in [r for r in legacy_rules if r["parent_rule_id"] is None]:
        type_models = bind.execute(
            sa.select(models).where(models.c.equipment_type_id == base["equipment_type_id"])
        ).mappings().all()

        children = {
            r["equipment_model_id"]: r
            for r in legacy_rules
            if r["parent_rule_id"] == base["id"] and r["equipment_model_id"] is not None
        }

        for model in type_models:
            source = children.get(model["id"], base)
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
                "is_active": bool(source["is_active"]),
                "description": source["description"],
            }
            new_id = bind.execute(
                sa.insert(rules).values(**values)
            ).inserted_primary_key[0]
            model_rules[(base["id"], model["id"])] = new_id
            for child_id, child in children.items():
                if child_id == model["id"]:
                    model_rules[(child["id"], model["id"])] = new_id

    # Repoint historical records to their model-specific rule where there is
    # no conflicting target record for the same equipment/date.
    legacy_ids = {r["id"] for r in legacy_rules}
    if legacy_ids:
        rec_rows = bind.execute(
            sa.select(records.c.id, records.c.equipment_id, records.c.rule_id, records.c.maintenance_date)
            .where(records.c.rule_id.in_(legacy_ids))
        ).mappings().all()
        for rec in rec_rows:
            eq = bind.execute(
                sa.select(equipment.c.equipment_model_id)
                .where(equipment.c.id == rec["equipment_id"])
            ).first()
            model_id = eq[0] if eq else None
            target_rule_id = model_rules.get((rec["rule_id"], model_id))
            if target_rule_id is None:
                # An exception maps through its base rule if needed.
                legacy = next((r for r in legacy_rules if r["id"] == rec["rule_id"]), None)
                if legacy and legacy["parent_rule_id"] is not None:
                    target_rule_id = model_rules.get((legacy["parent_rule_id"], model_id))
            if target_rule_id is None:
                continue
            conflict = bind.execute(
                sa.select(records.c.id).where(
                    records.c.equipment_id == rec["equipment_id"],
                    records.c.rule_id == target_rule_id,
                    records.c.maintenance_date == rec["maintenance_date"],
                )
            ).first()
            if conflict is None:
                bind.execute(
                    sa.update(records)
                    .where(records.c.id == rec["id"])
                    .values(rule_id=target_rule_id)
                )

    # Legacy type-level rules and old exception rows stay available for
    # historical inspection but can no longer participate in active schedules.
    bind.execute(
        sa.update(rules)
        .where(rules.c.equipment_model_id.is_(None))
        .values(is_active=False)
    )
    bind.execute(
        sa.update(rules)
        .where(rules.c.parent_rule_id.is_not(None))
        .values(is_active=False)
    )


def downgrade() -> None:
    bind = op.get_bind()
    if "maintenance_rules" not in sa.inspect(bind).get_table_names():
        return

    rules = sa.Table("maintenance_rules", sa.MetaData(), autoload_with=bind)
    # Do not delete model rules or historical data on downgrade. Just remove
    # the database guard; the 0004 schema remains structurally compatible.
    with op.batch_alter_table(
        "maintenance_rules",
        naming_convention={
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
        },
    ) as batch:
        if "ck_maintenance_rule_active_requires_model" in {
            c.get("name") for c in sa.inspect(bind).get_check_constraints("maintenance_rules")
        }:
            batch.drop_constraint("ck_maintenance_rule_active_requires_model", type_="check")
