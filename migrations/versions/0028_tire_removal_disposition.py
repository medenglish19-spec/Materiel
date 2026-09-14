"""add explicit tire removal disposition

revision: 0028
"""
from alembic import op
import sqlalchemy as sa

revision = "0028_tire_removal_disposition"
down_revision = "0027_tire_manual_expiry"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tire_movements", sa.Column("removal_disposition", sa.String(20), nullable=True))
    op.execute("UPDATE tire_movements SET removal_disposition = 'damaged' WHERE lower(trim(reason)) IN ('تالف', 'damaged', 'تلف') AND movement_type = 'remove'")
    op.execute("UPDATE tire_movements SET removal_disposition = 'expired' WHERE lower(trim(reason)) IN ('انتهاء الصلاحية', 'منتهي الصلاحية', 'expired') AND movement_type = 'remove'")
    op.execute("UPDATE tire_movements SET removal_disposition = 'stock' WHERE movement_type = 'remove' AND removal_disposition IS NULL")


def downgrade():
    op.drop_column("tire_movements", "removal_disposition")
