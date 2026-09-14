"""add precise timestamp to tire movements

revision: 0026
"""
from alembic import op
import sqlalchemy as sa

revision = "0026_tire_movement_datetime"
down_revision = "0025_merge_freeze_master_data"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tire_movements", sa.Column("movement_datetime", sa.DateTime(), nullable=True))
    op.execute("UPDATE tire_movements SET movement_datetime = movement_date")
    op.create_index("ix_tire_movements_movement_datetime", "tire_movements", ["movement_datetime"])


def downgrade():
    op.drop_index("ix_tire_movements_movement_datetime", table_name="tire_movements")
    op.drop_column("tire_movements", "movement_datetime")
