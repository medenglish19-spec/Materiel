"""Add linked spare-parts distribution and return documents."""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0034_spare_part_distribution_return"
down_revision: Union[str, Sequence[str], None] = ("0033_complete_technical_taxonomy", "add_received_date_spare_part_items")
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.create_table("spare_part_movement_documents",
        sa.Column("id", sa.Integer(), primary_key=True), sa.Column("document_number", sa.String(80), nullable=False),
        sa.Column("document_type", sa.String(20), nullable=False), sa.Column("document_date", sa.Date(), nullable=False),
        sa.Column("issuer", sa.String(160), nullable=False), sa.Column("recipient", sa.String(160), nullable=False),
        sa.Column("beneficiary", sa.String(200), nullable=True), sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("document_type IN ('distribution', 'return')", name="ck_spare_part_movement_document_type"),
        sa.UniqueConstraint("document_number", name="uq_spare_part_movement_document_number"))
    op.create_index("ix_spare_part_movement_documents_document_number", "spare_part_movement_documents", ["document_number"], unique=True)
    op.create_index("ix_spare_part_movement_documents_document_type", "spare_part_movement_documents", ["document_type"])
    op.create_index("ix_spare_part_movement_documents_document_date", "spare_part_movement_documents", ["document_date"])
    op.create_index("ix_spare_part_movement_documents_created_by_id", "spare_part_movement_documents", ["created_by_id"])
    op.create_table("spare_part_movement_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("spare_part_movement_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_item_id", sa.Integer(), sa.ForeignKey("spare_part_request_items.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=False), sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint("quantity > 0", name="ck_spare_part_movement_item_quantity_positive"),
        sa.UniqueConstraint("document_id", "request_item_id", name="uq_spare_part_movement_document_item"))
    op.create_index("ix_spare_part_movement_items_document_id", "spare_part_movement_items", ["document_id"])
    op.create_index("ix_spare_part_movement_items_request_item_id", "spare_part_movement_items", ["request_item_id"])

def downgrade() -> None:
    op.drop_table("spare_part_movement_items")
    op.drop_table("spare_part_movement_documents")
