"""add equipment model operating and component configuration

revision: 0020_model_equipment_configuration
down_revision: 0019_type_theoretical_quantity
"""
from alembic import op
import sqlalchemy as sa

revision = "0020_model_equipment_configuration"
down_revision = "0019_type_theoretical_quantity"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("equipment_models", sa.Column("has_tires", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("equipment_models", sa.Column("tire_positions_required", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("equipment_models", sa.Column("has_batteries", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("equipment_models", sa.Column("battery_count_required", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("equipment_models", sa.Column("mobility_type", sa.String(20), nullable=False, server_default="mobile"))
    op.add_column("equipment_models", sa.Column("requires_driver", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade():
    op.drop_column("equipment_models", "requires_driver")
    op.drop_column("equipment_models", "mobility_type")
    op.drop_column("equipment_models", "battery_count_required")
    op.drop_column("equipment_models", "has_batteries")
    op.drop_column("equipment_models", "tire_positions_required")
    op.drop_column("equipment_models", "has_tires")
