"""add extensible master-data configurations and model properties

Revision ID: 0020_master_data_configurations
Revises: 0019_type_theoretical_quantity
"""
from alembic import op
import sqlalchemy as sa

revision = "0020_master_data_configurations"
down_revision = "0019_type_theoretical_quantity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "master_data_configurations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("config_type", sa.String(40), nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("code", name="uq_master_data_configuration_code"),
    )
    op.create_index("ix_master_data_configurations_type", "master_data_configurations", ["config_type"])
    op.create_table(
        "master_data_configuration_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("configuration_id", sa.Integer(), sa.ForeignKey("master_data_configurations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_code", sa.String(80), nullable=False),
        sa.Column("item_name", sa.String(150), nullable=False),
        sa.Column("axle_number", sa.Integer(), nullable=True),
        sa.Column("side", sa.String(10), nullable=True),
        sa.Column("position_type", sa.String(20), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("value_text", sa.String(250), nullable=True),
        sa.Column("value_number", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(30), nullable=True),
        sa.Column("extra_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("configuration_id", "item_code", name="uq_master_data_configuration_item"),
    )
    op.create_index("ix_master_data_configuration_items_config", "master_data_configuration_items", ["configuration_id"])
    op.create_table(
        "master_data_model_properties",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("equipment_model_id", sa.Integer(), sa.ForeignKey("equipment_models.id", ondelete="CASCADE"), nullable=False),
        sa.Column("property_key", sa.String(80), nullable=False),
        sa.Column("property_label", sa.String(150), nullable=False),
        sa.Column("value_text", sa.String(250), nullable=True),
        sa.Column("value_number", sa.Float(), nullable=True),
        sa.Column("unit", sa.String(30), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("extra_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("equipment_model_id", "property_key", name="uq_master_data_model_property"),
    )
    op.create_index("ix_master_data_model_properties_model", "master_data_model_properties", ["equipment_model_id"])
    with op.batch_alter_table("equipment_models", recreate="always") as batch_op:
        batch_op.add_column(sa.Column("tire_configuration_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("battery_configuration_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key("fk_equipment_models_tire_configuration", "master_data_configurations", ["tire_configuration_id"], ["id"], ondelete="SET NULL")
        batch_op.create_foreign_key("fk_equipment_models_battery_configuration", "master_data_configurations", ["battery_configuration_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_equipment_models_tire_configuration", "equipment_models", ["tire_configuration_id"])
    op.create_index("ix_equipment_models_battery_configuration", "equipment_models", ["battery_configuration_id"])


def downgrade() -> None:
    op.drop_index("ix_equipment_models_battery_configuration", table_name="equipment_models")
    op.drop_index("ix_equipment_models_tire_configuration", table_name="equipment_models")
    with op.batch_alter_table("equipment_models", recreate="always") as batch_op:
        batch_op.drop_constraint("fk_equipment_models_battery_configuration", type_="foreignkey")
        batch_op.drop_constraint("fk_equipment_models_tire_configuration", type_="foreignkey")
        batch_op.drop_column("battery_configuration_id")
        batch_op.drop_column("tire_configuration_id")
    op.drop_index("ix_master_data_model_properties_model", table_name="master_data_model_properties")
    op.drop_table("master_data_model_properties")
    op.drop_index("ix_master_data_configuration_items_config", table_name="master_data_configuration_items")
    op.drop_table("master_data_configuration_items")
    op.drop_index("ix_master_data_configurations_type", table_name="master_data_configurations")
    op.drop_table("master_data_configurations")
