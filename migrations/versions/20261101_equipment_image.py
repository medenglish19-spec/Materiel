"""Add a photo field for individual equipment records."""
from alembic import op
import sqlalchemy as sa


revision = "20261101_equipment_image"
down_revision = "20261030_driver_model"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("equipment") as batch_op:
        batch_op.add_column(sa.Column("image_url", sa.String(length=500), nullable=True))


def downgrade():
    with op.batch_alter_table("equipment") as batch_op:
        batch_op.drop_column("image_url")
