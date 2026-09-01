"""add missions

revision: 0015
"""
from alembic import op
import sqlalchemy as sa

revision = "0015_missions"
down_revision = "0014_fuel"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "missions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("equipment_id", sa.Integer(), sa.ForeignKey("equipment.id", ondelete="CASCADE"), nullable=False),
        sa.Column("driver_name", sa.String(120), nullable=True),
        sa.Column("mission_document", sa.String(100), nullable=True),
        sa.Column("purpose", sa.String(250), nullable=True),
        sa.Column("destination", sa.String(150), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("departure_meter", sa.Numeric(10, 1), nullable=True),
        sa.Column("return_meter", sa.Numeric(10, 1), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.CheckConstraint("end_date IS NULL OR end_date >= start_date", name="ck_mission_dates"),
        sa.CheckConstraint("departure_meter IS NULL OR departure_meter >= 0", name="ck_mission_departure_meter"),
        sa.CheckConstraint("return_meter IS NULL OR return_meter >= 0", name="ck_mission_return_meter"),
    )
    op.create_index("ix_missions_equipment_id", "missions", ["equipment_id"])
    op.create_index("ix_missions_start_date", "missions", ["start_date"])
    op.create_index("ix_missions_end_date", "missions", ["end_date"])


def downgrade():
    op.drop_table("missions")
