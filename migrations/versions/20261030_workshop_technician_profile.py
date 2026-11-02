"""Store a free-text professional rank and registration number per technician."""
from alembic import op
import sqlalchemy as sa


revision = "20261030_tech_profile"
down_revision = "20261030_spare_part_equipment_models"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("workshop_technicians") as batch_op:
        batch_op.add_column(sa.Column("professional_rank", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("registration_number", sa.String(length=80), nullable=True))


def downgrade():
    with op.batch_alter_table("workshop_technicians") as batch_op:
        batch_op.drop_column("registration_number")
        batch_op.drop_column("professional_rank")
