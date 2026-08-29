"""add equipment classification hierarchy.

Revision ID: 0003_equipment_classification
Revises: 0002_remove_legacy_maintenance_columns
"""

from datetime import datetime, timezone

from alembic import op
from sqlalchemy import inspect
import sqlalchemy as sa


revision = "0003_equipment_classification"
down_revision = "0002_remove_legacy_maintenance_columns"
branch_labels = None
depends_on = None

_CATEGORIES = (
    ("المركبات الخفيفة", "LIGHT", 10),
    ("المركبات الثقيلة", "HEAVY", 20),
    ("معدات الأشغال", "CONSTRUCTION", 30),
    ("معدات الدعم", "SUPPORT", 40),
)


def _unique_constraint_for_columns(inspector, table_name: str, columns: list[str]):
    wanted = tuple(columns)
    for constraint in inspector.get_unique_constraints(table_name):
        if tuple(constraint.get("column_names") or ()) == wanted:
            return constraint.get("name")
    return None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "equipment_categories" not in tables:
        op.create_table(
            "equipment_categories",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("code", sa.String(length=30), nullable=False),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("name", name="uq_equipment_categories_name"),
            sa.UniqueConstraint("code", name="uq_equipment_category_code"),
        )

    inspector = inspect(bind)
    if "equipment_brands" not in inspector.get_table_names():
        op.create_table(
            "equipment_brands",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("name", name="uq_equipment_brands_name"),
        )

    categories = sa.table(
        "equipment_categories",
        sa.column("name", sa.String),
        sa.column("code", sa.String),
        sa.column("sort_order", sa.Integer),
        sa.column("is_system", sa.Boolean),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    existing_codes = {
        row[0] for row in bind.execute(
            sa.select(categories.c.code)
        ).fetchall()
    }
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    missing = [
        {
            "name": name,
            "code": code,
            "sort_order": sort_order,
            "is_system": True,
            "created_at": now,
            "updated_at": now,
        }
        for name, code, sort_order in _CATEGORIES
        if code not in existing_codes
    ]
    if missing:
        op.bulk_insert(categories, missing)

    inspector = inspect(bind)
    if "equipment_types" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("equipment_types")}
        if "category_id" not in columns:
            with op.batch_alter_table(
                "equipment_types",
                naming_convention={
                    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
                },
            ) as batch_op:
                batch_op.add_column(sa.Column("category_id", sa.Integer(), nullable=True))
                batch_op.create_foreign_key(
                    "fk_equipment_types_category",
                    "equipment_categories",
                    ["category_id"],
                    ["id"],
                    ondelete="SET NULL",
                )

    inspector = inspect(bind)
    if "equipment_models" in inspector.get_table_names():
        columns = {c["name"] for c in inspector.get_columns("equipment_models")}
        old_constraint = _unique_constraint_for_columns(
            inspector, "equipment_models", ["equipment_type_id", "name"]
        )
        new_constraint = _unique_constraint_for_columns(
            inspector, "equipment_models",
            ["equipment_type_id", "brand_id", "name"]
        )
        fks = {c.get("name") for c in inspector.get_foreign_keys("equipment_models")}

        with op.batch_alter_table(
            "equipment_models",
            naming_convention={
                "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
            },
        ) as batch_op:
            if "brand_id" not in columns:
                batch_op.add_column(sa.Column("brand_id", sa.Integer(), nullable=True))
            if "fk_equipment_models_brand" not in fks:
                batch_op.create_foreign_key(
                    "fk_equipment_models_brand",
                    "equipment_brands",
                    ["brand_id"],
                    ["id"],
                    ondelete="SET NULL",
                )
            if old_constraint and not new_constraint:
                batch_op.drop_constraint(old_constraint, type_="unique")
                batch_op.create_unique_constraint(
                    "uq_model_per_type_brand",
                    ["equipment_type_id", "brand_id", "name"],
                )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if "equipment_models" in inspector.get_table_names():
        with op.batch_alter_table(
            "equipment_models",
            naming_convention={
                "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
            },
        ) as batch_op:
            constraint = _unique_constraint_for_columns(
                inspector, "equipment_models",
                ["equipment_type_id", "brand_id", "name"]
            )
            if constraint:
                batch_op.drop_constraint(constraint, type_="unique")
            if "fk_equipment_models_brand" in {
                c.get("name") for c in inspector.get_foreign_keys("equipment_models")
            }:
                batch_op.drop_constraint("fk_equipment_models_brand", type_="foreignkey")
            if "brand_id" in {c["name"] for c in inspector.get_columns("equipment_models")}:
                batch_op.drop_column("brand_id")
            if _unique_constraint_for_columns(
                inspector, "equipment_models", ["equipment_type_id", "name"]
            ) is None:
                batch_op.create_unique_constraint(
                    "uq_model_per_type", ["equipment_type_id", "name"]
                )

    inspector = inspect(bind)
    if "equipment_types" in inspector.get_table_names():
        with op.batch_alter_table(
            "equipment_types",
            naming_convention={
                "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
            },
        ) as batch_op:
            if "fk_equipment_types_category" in {
                c.get("name") for c in inspector.get_foreign_keys("equipment_types")
            }:
                batch_op.drop_constraint("fk_equipment_types_category", type_="foreignkey")
            if "category_id" in {c["name"] for c in inspector.get_columns("equipment_types")}:
                batch_op.drop_column("category_id")

    inspector = inspect(bind)
    if "equipment_brands" in inspector.get_table_names():
        op.drop_table("equipment_brands")
    if "equipment_categories" in inspector.get_table_names():
        op.drop_table("equipment_categories")
