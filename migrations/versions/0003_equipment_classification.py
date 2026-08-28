"""add equipment classification hierarchy.

Revision ID: 0003_equipment_classification
Revises: 0002_remove_legacy_maintenance_columns
"""

from alembic import op
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


def upgrade() -> None:
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
    op.create_table(
        "equipment_brands",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", name="uq_equipment_brands_name"),
    )

    category_table = sa.table(
        "equipment_categories",
        sa.column("name", sa.String),
        sa.column("code", sa.String),
        sa.column("sort_order", sa.Integer),
        sa.column("is_system", sa.Boolean),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    now = sa.func.current_timestamp()
    op.bulk_insert(
        category_table,
        [
            {
                "name": name,
                "code": code,
                "sort_order": sort_order,
                "is_system": True,
                "created_at": now,
                "updated_at": now,
            }
            for name, code, sort_order in _CATEGORIES
        ],
    )

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

    with op.batch_alter_table(
        "equipment_models",
        naming_convention={"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"},
    ) as batch_op:
        batch_op.add_column(sa.Column("brand_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_equipment_models_brand",
            "equipment_brands",
            ["brand_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.drop_constraint("uq_model_per_type", type_="unique")
        batch_op.create_unique_constraint(
            "uq_model_per_type_brand",
            ["equipment_type_id", "brand_id", "name"],
        )


def downgrade() -> None:
    with op.batch_alter_table(
        "equipment_models",
        naming_convention={"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"},
    ) as batch_op:
        batch_op.drop_constraint("uq_model_per_type_brand", type_="unique")
        batch_op.drop_constraint("fk_equipment_models_brand", type_="foreignkey")
        batch_op.drop_column("brand_id")
        batch_op.create_unique_constraint("uq_model_per_type", ["equipment_type_id", "name"])

    with op.batch_alter_table(
        "equipment_types",
        naming_convention={"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"},
    ) as batch_op:
        batch_op.drop_constraint("fk_equipment_types_category", type_="foreignkey")
        batch_op.drop_column("category_id")

    op.drop_table("equipment_brands")
    op.drop_table("equipment_categories")
