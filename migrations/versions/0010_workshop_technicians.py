"""add internal workshop technicians and interventions
revision: 0010
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_workshop_technicians"
down_revision = "0009_spare_part_receiving_document"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table(
        "workshop_technicians",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_number", sa.String(50), nullable=False),
        sa.Column("full_name", sa.String(160), nullable=False),
        sa.Column("specialization", sa.String(120), nullable=True),
        sa.Column("is_active", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.UniqueConstraint("employee_number", name="uq_workshop_technician_employee_number"),
    )
    op.create_index("ix_workshop_technicians_employee_number", "workshop_technicians", ["employee_number"])
    op.create_index("ix_workshop_technicians_full_name", "workshop_technicians", ["full_name"])
    op.create_table(
        "technician_interventions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("repair_id", sa.Integer(), sa.ForeignKey("repairs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("technician_id", sa.Integer(), sa.ForeignKey("workshop_technicians.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("intervention_date", sa.Date(), nullable=False),
        sa.Column("hours", sa.Numeric(8,1), nullable=False, server_default="0"),
        sa.Column("work_description", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint("hours >= 0", name="ck_technician_intervention_hours_nonnegative"),
        sa.UniqueConstraint("repair_id", "technician_id", name="uq_repair_technician"),
    )
    op.create_index("ix_technician_interventions_repair_id", "technician_interventions", ["repair_id"])
    op.create_index("ix_technician_interventions_technician_id", "technician_interventions", ["technician_id"])

def downgrade():
    op.drop_index("ix_technician_interventions_technician_id", table_name="technician_interventions")
    op.drop_index("ix_technician_interventions_repair_id", table_name="technician_interventions")
    op.drop_table("technician_interventions")
    op.drop_index("ix_workshop_technicians_full_name", table_name="workshop_technicians")
    op.drop_index("ix_workshop_technicians_employee_number", table_name="workshop_technicians")
    op.drop_table("workshop_technicians")
