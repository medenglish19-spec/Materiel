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


def _table_exists(inspector, name: str) -> bool:
    return name in inspector.get_table_names()


def _unique_constraint_for_columns(inspector, table_name: str, columns: list[str]):
    wanted = tuple(columns)
    for constraint in inspector.get_unique_constraints(table_name):
        if tuple(constraint.get("column_names") or ()) == wanted:
            return constraint.get("name")
    return None


def upgrade() -> None:
    """Apply classification changes safely on an existing SQLite/PostgreSQL schema."""
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    # Make the migration retry-safe. This is important if an earlier startup
    # stopped after creating one of the tables but before completing the batch.
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
    tables = set(inspector.get_table_names())
    if "equipment_brands" not in tables:
        op.create_table(
            "equipment_brands",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("name", name="uq_equipment_brands_name"),
        )

    # Seed only missing system categories. Existing user data is untouched.
    category_table = sa.table(
        "equipment_categories",
        sa.column("name", sa.String),
        sa.column("code", sa.String),
        sa.column("sort_order", sa.Integer),
        sa.column("is_system", sa.Boolean),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    existing_codes = {
        row[0]
        for row in bind.execute(sa.select(category_table.c.code)).fetchall()
    }
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
        op.bulk_insert(category_table, missing)

    inspector = inspect(bind)

    # Add the nullable FKs only if they are not already present.
    type_columns = {c["name"] for c in inspector.get_columns("equipment_types")}
    model_columns = {c["name"] for c in inspector.get_columns("equipment_models")}

    if "category_id" not in type_columns:
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
    if "brand_id" not in model_columns:
        with op.batch_alter_table(
            "equipment_models",
            naming_convention={
                "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
            },
        ) as batch_op:
            batch_op.add_column(sa.Column("brand_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                "fk_equipment_models_brand",
                "equipment_brands",
                ["brand_id"],
                ["id"],
                ondelete="SET NULL",
            )

    # Change the old uniqueness rule only when it is actually present.
    # A unique index is used for the new rule on SQLite because SQLite's
    # nullable-column semantics make the desired model/brand/name combination
    # safer to express as an index without rebuilding an already populated table.
    inspector = inspect(bind)
    old_constraint = _unique_constraint_for_columns(
        inspector,
        "equipment_models",
        ["equipment_type_id", "name"],
    )
    new_columns = ["equipment_type_id", "brand_id", "name"]
    new_constraint = _unique_constraint_for_columns(
        inspector,
        "equipment_models",
        new_columns,
    )

    if old_constraint and not new_constraint:
        with op.batch_alter_table(
            "equipment_models",
            naming_convention={
                "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
            },
        ) as batch_op:
            batch_op.drop_constraint(old_constraint, type_="unique")
            batch_op.create_unique_constraint(
                "uq_model_per_type_brand",
                new_columns,
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    if _table_exists(inspector, "equipment_models"):
        with op.batch_alter_table(
            "equipment_models",
            naming_convention={
                "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
            },
        ) as batch_op:
            new_constraint = _unique_constraint_for_columns(
                inspector,
                "equipment_models",
                ["equipment_type_id", "brand_id", "name"],
            )
            if new_constraint:
                batch_op.drop_constraint(new_constraint, type_="unique")
            batch_op.drop_column("brand_id")

    inspector = inspect(bind)
    if _table_exists(inspector, "equipment_types"):
        with op.batch_alter_table(
            "equipment_types",
            naming_convention={
                "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"
            },
        ) as batch_op:
            batch_op.drop_column("category_id")

    inspector = inspect(bind)
    if _table_exists(inspector, "equipment_brands"):
        op.drop_table("equipment_brands")
    if _table_exists(inspector, "equipment_categories"):
        op.drop_table("equipment_categories")
