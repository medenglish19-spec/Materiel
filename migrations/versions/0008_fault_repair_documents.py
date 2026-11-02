"""add fault report fields and repair workshop/document controls

revision: 0008
"""
from alembic import op
import sqlalchemy as sa


revision = "0008_fault_repair_documents"
down_revision = "0007_faults_repairs"
branch_labels = None
depends_on = None

_FOREIGN_KEY_NAMING_CONVENTION = {"fk": "fk_%(table_name)s_%(column_0_name)s"}


def upgrade() -> None:
    op.add_column("faults", sa.Column("report_number", sa.String(80), nullable=True))
    op.add_column("faults", sa.Column("note", sa.Text(), nullable=True))
    op.create_index("ix_faults_report_number", "faults", ["report_number"])

    op.add_column("repairs", sa.Column("workshop_type", sa.String(20), nullable=False, server_default="internal"))
    op.add_column("repairs", sa.Column("repair_document", sa.String(255), nullable=True))
    op.add_column("repairs", sa.Column("external_dispatch_document", sa.String(255), nullable=True))
    op.add_column("repair_parts", sa.Column("distribution_document", sa.String(255), nullable=True))
    with op.batch_alter_table(
        "repairs", naming_convention=_FOREIGN_KEY_NAMING_CONVENTION
    ) as batch_op:
        batch_op.create_check_constraint(
            "ck_repair_workshop_type",
            "workshop_type IN ('internal', 'external')",
        )
        batch_op.create_check_constraint(
            "ck_external_repair_requires_dispatch_document",
            "(workshop_type = 'internal') OR external_dispatch_document IS NOT NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table(
        "repairs", naming_convention=_FOREIGN_KEY_NAMING_CONVENTION
    ) as batch_op:
        batch_op.drop_constraint("ck_external_repair_requires_dispatch_document", type_="check")
        batch_op.drop_constraint("ck_repair_workshop_type", type_="check")
        batch_op.drop_column("external_dispatch_document")
        batch_op.drop_column("repair_document")
        batch_op.drop_column("workshop_type")
    with op.batch_alter_table(
        "repair_parts", naming_convention=_FOREIGN_KEY_NAMING_CONVENTION
    ) as batch_op:
        batch_op.drop_column("distribution_document")
    op.drop_index("ix_faults_report_number", table_name="faults")
    with op.batch_alter_table(
        "faults", naming_convention=_FOREIGN_KEY_NAMING_CONVENTION
    ) as batch_op:
        batch_op.drop_column("note")
        batch_op.drop_column("report_number")
