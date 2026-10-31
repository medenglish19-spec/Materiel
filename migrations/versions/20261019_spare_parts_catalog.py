"""Add catalog metadata around the existing spare_parts identity."""
from alembic import op
import sqlalchemy as sa


revision = "20261019_spare_parts_catalog"
down_revision = "20261018_tire_battery_asset_receipts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "spare_part_categories",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("name_ar", sa.String(120), nullable=False),
        sa.Column("name_fr", sa.String(120), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["parent_id"], ["spare_part_categories.id"], name="fk_spare_part_categories_parent_id", ondelete="RESTRICT"),
    )
    op.create_index("ix_spare_part_categories_parent_id", "spare_part_categories", ["parent_id"])
    op.create_table(
        "spare_part_catalog_details",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("spare_part_id", sa.Integer(), nullable=False),
        sa.Column("category_id", sa.Integer(), nullable=True),
        sa.Column("name_ar", sa.String(160), nullable=True),
        sa.Column("name_fr", sa.String(160), nullable=True),
        sa.Column("original_name", sa.String(255), nullable=True),
        sa.Column("manufacturer", sa.String(160), nullable=True),
        sa.Column("source", sa.String(255), nullable=True),
        sa.Column("image_path", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["spare_part_id"], ["spare_parts.id"], name="fk_spare_part_catalog_details_spare_part_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["spare_part_categories.id"], name="fk_spare_part_catalog_details_category_id", ondelete="RESTRICT"),
        sa.UniqueConstraint("spare_part_id", name="uq_spare_part_catalog_details_spare_part_id"),
    )
    op.create_index("ix_spare_part_catalog_details_spare_part_id", "spare_part_catalog_details", ["spare_part_id"])
    op.create_index("ix_spare_part_catalog_details_category_id", "spare_part_catalog_details", ["category_id"])
    op.create_index("ix_spare_part_catalog_details_manufacturer", "spare_part_catalog_details", ["manufacturer"])
    op.create_index("ix_spare_part_catalog_details_is_active", "spare_part_catalog_details", ["is_active"])
    op.create_table(
        "spare_part_catalog_references",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("spare_part_id", sa.Integer(), nullable=False),
        sa.Column("manufacturer", sa.String(160), nullable=True),
        sa.Column("reference", sa.String(120), nullable=False),
        sa.Column("reference_type", sa.String(40), nullable=False, server_default="manufacturer"),
        sa.Column("source", sa.String(255), nullable=True),
        sa.ForeignKeyConstraint(["spare_part_id"], ["spare_parts.id"], name="fk_spare_part_catalog_references_spare_part_id", ondelete="CASCADE"),
    )
    op.create_index("ix_spare_part_catalog_references_spare_part_id", "spare_part_catalog_references", ["spare_part_id"])
    op.create_index("ix_spare_part_catalog_ref_lookup", "spare_part_catalog_references", ["manufacturer", "reference"])
    op.create_table(
        "spare_part_catalog_imports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("file_type", sa.String(16), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="preview"),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], name="fk_spare_part_catalog_imports_created_by", ondelete="SET NULL"),
    )
    op.create_index("ix_spare_part_catalog_imports_content_sha256", "spare_part_catalog_imports", ["content_sha256"])
    op.create_index("ix_spare_part_catalog_imports_status", "spare_part_catalog_imports", ["status"])


def downgrade():
    op.drop_index("ix_spare_part_catalog_imports_status", table_name="spare_part_catalog_imports")
    op.drop_index("ix_spare_part_catalog_imports_content_sha256", table_name="spare_part_catalog_imports")
    op.drop_table("spare_part_catalog_imports")
    op.drop_index("ix_spare_part_catalog_ref_lookup", table_name="spare_part_catalog_references")
    op.drop_index("ix_spare_part_catalog_references_spare_part_id", table_name="spare_part_catalog_references")
    op.drop_table("spare_part_catalog_references")
    op.drop_index("ix_spare_part_catalog_details_is_active", table_name="spare_part_catalog_details")
    op.drop_index("ix_spare_part_catalog_details_manufacturer", table_name="spare_part_catalog_details")
    op.drop_index("ix_spare_part_catalog_details_category_id", table_name="spare_part_catalog_details")
    op.drop_index("ix_spare_part_catalog_details_spare_part_id", table_name="spare_part_catalog_details")
    op.drop_table("spare_part_catalog_details")
    op.drop_index("ix_spare_part_categories_parent_id", table_name="spare_part_categories")
    op.drop_table("spare_part_categories")
