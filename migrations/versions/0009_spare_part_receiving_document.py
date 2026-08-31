"""finalize spare-part receiving document

revision: 0009
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_spare_part_receiving_document"
down_revision = "0008_fault_repair_documents"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("spare_parts", sa.Column("receiving_document", sa.String(255), nullable=True))
    op.drop_constraint("ck_spare_part_active", "spare_parts", type_="check")
    op.drop_column("spare_parts", "unit")
    op.drop_column("spare_parts", "is_active")


def downgrade() -> None:
    op.add_column("spare_parts", sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"))
    op.add_column("spare_parts", sa.Column("unit", sa.String(30), nullable=False, server_default="قطعة"))
    op.create_check_constraint("ck_spare_part_active", "spare_parts", "is_active IN (0, 1)")
    op.drop_column("spare_parts", "receiving_document")
