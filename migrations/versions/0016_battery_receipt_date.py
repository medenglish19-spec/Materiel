"""add battery receipt date
revision: 0016
"""
from alembic import op
import sqlalchemy as sa
revision = "0016_battery_receipt_date"
down_revision = "0015_missions"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("batteries", sa.Column("receipt_date", sa.Date(), nullable=True))

def downgrade():
    op.drop_column("batteries", "receipt_date")
