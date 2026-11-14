"""Store versioned manufacturer maintenance catalogs for review.

Revision ID: 20261020_maintenance_catalog_imports
Revises: 20261019_spare_parts_catalog
"""
from alembic import op
import sqlalchemy as sa


revision = "20261020_maintenance_catalog_imports"
down_revision = "20261019_spare_parts_catalog"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "maintenance_catalog_imports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("equipment_model_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("manufacturer", sa.String(160), nullable=True),
        sa.Column("document_title", sa.String(255), nullable=True),
        sa.Column("document_version", sa.String(120), nullable=True),
        sa.Column("filename", sa.String(255), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("file_type", sa.String(16), nullable=False),
        sa.Column("source_file", sa.LargeBinary(), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=False),
        sa.Column("items_json", sa.Text(), nullable=False),
        sa.Column("warnings_json", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("reviewed_by_id", sa.Integer(), nullable=True),
        sa.CheckConstraint("status IN ('draft', 'reviewed', 'applied', 'rejected')", name="ck_maintenance_catalog_import_status"),
        sa.UniqueConstraint("equipment_model_id", "content_sha256", name="uq_maintenance_catalog_model_sha256"),
        sa.ForeignKeyConstraint(["equipment_model_id"], ["equipment_models.id"], name="fk_maintenance_catalog_imports_equipment_model", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], name="fk_maintenance_catalog_imports_created_by", ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"], name="fk_maintenance_catalog_imports_reviewed_by", ondelete="SET NULL"),
    )
    op.create_index("ix_maintenance_catalog_imports_equipment_model_id", "maintenance_catalog_imports", ["equipment_model_id"])
    op.create_index("ix_maintenance_catalog_imports_content_sha256", "maintenance_catalog_imports", ["content_sha256"])
    op.create_index("ix_maintenance_catalog_imports_status", "maintenance_catalog_imports", ["status"])
    op.create_index("ix_maintenance_catalog_imports_created_by_id", "maintenance_catalog_imports", ["created_by_id"])
    op.create_index("ix_maintenance_catalog_imports_reviewed_by_id", "maintenance_catalog_imports", ["reviewed_by_id"])


def downgrade():
    op.drop_index("ix_maintenance_catalog_imports_reviewed_by_id", table_name="maintenance_catalog_imports")
    op.drop_index("ix_maintenance_catalog_imports_created_by_id", table_name="maintenance_catalog_imports")
    op.drop_index("ix_maintenance_catalog_imports_status", table_name="maintenance_catalog_imports")
    op.drop_index("ix_maintenance_catalog_imports_content_sha256", table_name="maintenance_catalog_imports")
    op.drop_index("ix_maintenance_catalog_imports_equipment_model_id", table_name="maintenance_catalog_imports")
    op.drop_table("maintenance_catalog_imports")
