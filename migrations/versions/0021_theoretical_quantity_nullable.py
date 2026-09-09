"""allow blank theoretical quantity for equipment types

revision: 0021_theoretical_quantity_nullable
down_revision: 0020_model_equipment_configuration
"""
from alembic import op
import sqlalchemy as sa

revision = "0021_theoretical_quantity_nullable"
down_revision = "0020_model_equipment_configuration"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("equipment_types", recreate="auto") as batch_op:
        batch_op.alter_column("theoretical_quantity", existing_type=sa.Integer(), nullable=True, server_default=None)


def downgrade():
    op.execute("UPDATE equipment_types SET theoretical_quantity = 0 WHERE theoretical_quantity IS NULL")
    with op.batch_alter_table("equipment_types", recreate="auto") as batch_op:
        batch_op.alter_column("theoretical_quantity", existing_type=sa.Integer(), nullable=False, server_default="0")
