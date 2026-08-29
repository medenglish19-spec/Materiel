"""add equipment classification hierarchy.

Revision ID: 0003_equipment_classification
Revises: 0002_remove_legacy_maintenance_columns
"""

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


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
            sa.select(sa.column("code")).select_from(sa.table("equipment_categories"))
        )
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

    if "equipment_types" in tables:
        columns = {c["name"] for c in inspector.get_columns("equipment_types")}
        if "category_id" not in columns:
            with op.batch_alter_table(
                "equipment_types",
                naming_convention={"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"},
            ) as batch_op:
                batch_op.add_column(sa.Column("category_id", sa.Integer(), nullable=True))
                batch_op.create_foreign_key(
                    "fk_equipment_types_category",
                    "equipment_categories",
                    ["category_id"],
                    ["id"],
                    ondelete="SET NULL",
                )

    if "equipment_models" in tables:
        columns = {c["name"] for c in inspector.get_columns("equipment_models")}
        constraints = {c["name"] for c in inspector.get_unique_constraints("equipment_models")}
        fks = {c["name"] for c in inspector.get_foreign_keys("equipment_models")}
        with op.batch_alter_table(
            "equipment_models",
            naming_convention={"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"},
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
            if "uq_model_per_type" in constraints:
                batch_op.drop_constraint("uq_model_per_type", type_="unique")
            if "uq_model_per_type_brand" not in constraints:
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
            naming_convention={"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"},
        ) as batch_op:
            constraints = {c["name"] for c in inspector.get_unique_constraints("equipment_models")}
            fks = {c["name"] for c in inspector.get_foreign_keys("equipment_models")}
            if "uq_model_per_type_brand" in constraints:
                batch_op.drop_constraint("uq_model_per_type_brand", type_="unique")
            if "fk_equipment_models_brand" in fks:
                batch_op.drop_constraint("fk_equipment_models_brand", type_="foreignkey")
            if "brand_id" in {c["name"] for c in inspector.get_columns("equipment_models")}:
                batch_op.drop_column("brand_id")
            if "uq_model_per_type" not in constraints:
                batch_op.create_unique_constraint("uq_model_per_type", ["equipment_type_id", "name"])

    if "equipment_types" in inspector.get_table_names():
        with op.batch_alter_table(
            "equipment_types",
            naming_convention={"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"},
        ) as batch_op:
            fks = {c["name"] for c in inspector.get_foreign_keys("equipment_types")}
            if "fk_equipment_types_category" in fks:
                batch_op.drop_constraint("fk_equipment_types_category", type_="foreignkey")
            if "category_id" in {c["name"] for c in inspector.get_columns("equipment_types")}:
                batch_op.drop_column("category_id")

    if "equipment_brands" in inspector.get_table_names():
        op.drop_table("equipment_brands")
    if "equipment_categories" in inspector.get_table_names():
        op.drop_table("equipment_categories")
