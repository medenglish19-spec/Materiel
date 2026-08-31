"""add fault report fields and repair workshop/document controls

revision: 0008
"""
from alembic import op
import sqlalchemy as sa


revision = "0008_fault_repair_documents"
down_revision = "0007_faults_repairs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("faults", sa.Column("report_number", sa.String(80), nullable=True))
    op.add_column("faults", sa.Column("note", sa.Text(), nullable=True))
    op.create_index("ix_faults_report_number", "faults", ["report_number"])

    op.add_column("repairs", sa.Column("workshop_type", sa.String(20), nullable=False, server_default="internal"))
    op.add_column("repairs", sa.Column("repair_document", sa.String(255), nullable=True))
    op.add_column("repairs", sa.Column("external_dispatch_document", sa.String(255), nullable=True))
    op.add_column("repair_parts", sa.Column("distribution_document", sa.String(255), nullable=True))
    op.alter_column("repair_parts", "distribution_document", nullable=False)
    op.create_check_constraint(
        "ck_repair_workshop_type", "repairs",
        "workshop_type IN ('internal', 'external')",
    )
    op.create_check_constraint(
        "ck_external_repair_requires_dispatch_document", "repairs",
        "(workshop_type = 'internal') OR external_dispatch_document IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ck_external_repair_requires_dispatch_document", "repairs", type_="check")
    op.drop_constraint("ck_repair_workshop_type", "repairs", type_="check")
    op.drop_column("repair_parts", "distribution_document")
    op.drop_column("repairs", "external_dispatch_document")
    op.drop_column("repairs", "repair_document")
    op.drop_column("repairs", "workshop_type")
    op.drop_index("ix_faults_report_number", table_name="faults")
    op.drop_column("faults", "note")
    op.drop_column("faults", "report_number")
