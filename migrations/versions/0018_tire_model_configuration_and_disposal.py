"""model-specific tire configuration, central validity, and disposal records

revision: 0018
down_revision: 0017_tire_receipt_date
"""
from alembic import op
import sqlalchemy as sa

revision = "0018_tire_model_configuration"
down_revision = "0017_tire_receipt_date"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tire_positions", sa.Column("equipment_model_id", sa.Integer(), sa.ForeignKey("equipment_models.id", ondelete="CASCADE"), nullable=True))
    op.add_column("tire_positions", sa.Column("axle_number", sa.Integer(), nullable=True))
    op.add_column("tire_positions", sa.Column("side", sa.String(10), nullable=True))
    op.add_column("tire_positions", sa.Column("position_type", sa.String(20), nullable=True))
    op.create_index("ix_tire_positions_equipment_model_id", "tire_positions", ["equipment_model_id"])
    op.create_index("ix_tire_positions_model_axle", "tire_positions", ["equipment_model_id", "axle_number"])
    op.create_table("tire_model_sizes", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("equipment_model_id", sa.Integer(), sa.ForeignKey("equipment_models.id", ondelete="CASCADE"), nullable=False), sa.Column("size", sa.String(50), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("equipment_model_id", "size", name="uq_tire_model_size"))
    op.create_index("ix_tire_model_sizes_model", "tire_model_sizes", ["equipment_model_id"])
    op.create_table("tire_system_settings", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("validity_years", sa.Integer(), nullable=False, server_default="3"), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False))
    op.execute("INSERT INTO tire_system_settings (id, validity_years, created_at, updated_at) VALUES (1, 3, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)")
    op.create_table("tire_disposals", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("tire_id", sa.Integer(), sa.ForeignKey("tires.id", ondelete="CASCADE"), nullable=False), sa.Column("disposal_date", sa.Date(), nullable=False), sa.Column("disposal_document", sa.String(100), nullable=False), sa.Column("reason", sa.String(250), nullable=False), sa.Column("notes", sa.Text(), nullable=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("tire_id", name="uq_tire_disposal_tire"))
    op.create_index("ix_tire_disposals_tire_id", "tire_disposals", ["tire_id"])


def downgrade():
    op.drop_table("tire_disposals")
    op.drop_table("tire_system_settings")
    op.drop_index("ix_tire_model_sizes_model", table_name="tire_model_sizes")
    op.drop_table("tire_model_sizes")
    op.drop_index("ix_tire_positions_model_axle", table_name="tire_positions")
    op.drop_index("ix_tire_positions_equipment_model_id", table_name="tire_positions")
    op.drop_column("tire_positions", "position_type")
    op.drop_column("tire_positions", "side")
    op.drop_column("tire_positions", "axle_number")
    op.drop_column("tire_positions", "equipment_model_id")
