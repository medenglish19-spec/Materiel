"""add axle_count to equipment_models

revision: 0030
down_revision: 0029_tire_movement_datetime_integrity
"""
from alembic import op
import sqlalchemy as sa

revision = "0030_model_axle_count"
down_revision = "0029_tire_movement_datetime_integrity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("equipment_models")}
    if "axle_count" not in columns:
        op.add_column("equipment_models", sa.Column("axle_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("equipment_models")}
    if "axle_count" in columns:
        with op.batch_alter_table("equipment_models") as batch_op:
            batch_op.drop_column("axle_count")