"""Add start and end dates to repair records.

Existing repair rows are preserved; the new dates are nullable for historical records.
"""
from alembic import op
import sqlalchemy as sa

revision = "0053_repair_start_end_dates"
down_revision = "merge_stage11_c3a9e7f21d04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("repairs", sa.Column("repair_start_date", sa.Date(), nullable=True))
    op.add_column("repairs", sa.Column("repair_end_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("repairs", "repair_end_date")
    op.drop_column("repairs", "repair_start_date")
