"""Store reference fuel consumption rates for equipment models."""

from alembic import op
import sqlalchemy as sa


revision = "20261024_fuel_model_consumption_rates"
down_revision = "20261024_battery_capacity"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "fuel_model_consumption_rates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("equipment_model_id", sa.Integer(), nullable=False),
        sa.Column("fuel_type", sa.String(length=40), nullable=False),
        sa.Column("consumption_rate", sa.Numeric(10, 2), nullable=False),
        sa.Column("measurement_unit", sa.String(length=30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.current_timestamp()),
        sa.ForeignKeyConstraint(
            ["equipment_model_id"], ["equipment_models.id"],
            name="fk_fuel_model_rate_model", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_fuel_model_consumption_rates"),
        sa.UniqueConstraint("equipment_model_id", "fuel_type", name="uq_fuel_model_rate_model_type"),
    )
    op.create_index(
        "ix_fuel_model_consumption_rates_equipment_model_id",
        "fuel_model_consumption_rates", ["equipment_model_id"], unique=False,
    )


def downgrade():
    op.drop_index(
        "ix_fuel_model_consumption_rates_equipment_model_id",
        table_name="fuel_model_consumption_rates",
    )
    op.drop_table("fuel_model_consumption_rates")
