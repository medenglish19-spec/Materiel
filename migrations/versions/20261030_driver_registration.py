"""Add a registration number field to driver records."""
from alembic import op
import sqlalchemy as sa


revision = "20261030_driver_reg"
down_revision = "20261030_tech_profile"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("drivers") as batch_op:
        batch_op.add_column(sa.Column("registration_number", sa.String(length=80), nullable=True))


def downgrade():
    with op.batch_alter_table("drivers") as batch_op:
        batch_op.drop_column("registration_number")
