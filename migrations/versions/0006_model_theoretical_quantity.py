"""add theoretical quantity to equipment models

revision: 0006
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_model_theoretical_quantity"
down_revision = "0005_model_only_maintenance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "equipment_models",
        sa.Column("theoretical_quantity", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("equipment_models", "theoretical_quantity")
