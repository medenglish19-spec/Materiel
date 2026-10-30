"""Link spare-part catalog entries to compatible equipment models."""
from alembic import op
import sqlalchemy as sa


revision = "20261030_spare_part_equipment_models"
down_revision = "20261025_unify_asset_receiving"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "spare_part_catalog_models",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("spare_part_id", sa.Integer(), nullable=False),
        sa.Column("equipment_model_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["spare_part_id"], ["spare_parts.id"], name="fk_spare_part_catalog_models_spare_part_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["equipment_model_id"], ["equipment_models.id"], name="fk_spare_part_catalog_models_equipment_model_id", ondelete="CASCADE"),
        sa.UniqueConstraint("spare_part_id", "equipment_model_id", name="uq_spare_part_catalog_model"),
    )
    op.create_index("ix_spare_part_catalog_models_spare_part_id", "spare_part_catalog_models", ["spare_part_id"])
    op.create_index("ix_spare_part_catalog_models_equipment_model_id", "spare_part_catalog_models", ["equipment_model_id"])


def downgrade():
    op.drop_index("ix_spare_part_catalog_models_equipment_model_id", table_name="spare_part_catalog_models")
    op.drop_index("ix_spare_part_catalog_models_spare_part_id", table_name="spare_part_catalog_models")
    op.drop_table("spare_part_catalog_models")
