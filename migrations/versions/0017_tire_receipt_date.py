"""add tire receipt date
revision: 0017
"""
from alembic import op
import sqlalchemy as sa
revision = "0017_tire_receipt_date"
down_revision = "0016_battery_receipt_date"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("tires", sa.Column("receipt_date", sa.Date(), nullable=True))

def downgrade():
    op.drop_column("tires", "receipt_date")
