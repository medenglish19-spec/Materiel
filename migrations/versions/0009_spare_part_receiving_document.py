"""finalize spare-part receiving document

revision: 0009
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_spare_part_receiving_document"
down_revision = "0008_fault_repair_documents"
branch_labels = None
depends_on = None

_FOREIGN_KEY_NAMING_CONVENTION = {"fk": "fk_%(table_name)s_%(column_0_name)s"}


def upgrade() -> None:
    op.add_column("spare_parts", sa.Column("receiving_document", sa.String(255), nullable=True))
    with op.batch_alter_table(
        "spare_parts", naming_convention=_FOREIGN_KEY_NAMING_CONVENTION
    ) as batch_op:
        batch_op.drop_constraint("ck_spare_part_active", type_="check")
        batch_op.drop_column("unit")
        batch_op.drop_column("is_active")


def downgrade() -> None:
    with op.batch_alter_table(
        "spare_parts", naming_convention=_FOREIGN_KEY_NAMING_CONVENTION
    ) as batch_op:
        batch_op.add_column(sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"))
        batch_op.add_column(sa.Column("unit", sa.String(30), nullable=False, server_default="قطعة"))
        batch_op.create_check_constraint("ck_spare_part_active", "is_active IN (0, 1)")
        batch_op.drop_column("receiving_document")
