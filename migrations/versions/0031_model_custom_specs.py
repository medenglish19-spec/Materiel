"""add equipment model custom specs

revision: 0031
down_revision: 0030_model_axle_count
"""
from alembic import op
import sqlalchemy as sa
revision="0031_model_custom_specs"
down_revision="0030_model_axle_count"
branch_labels=None
depends_on=None
def upgrade():
    bind=op.get_bind();tables=set(sa.inspect(bind).get_table_names())
    if "equipment_model_spec_definitions" not in tables: op.create_table("equipment_model_spec_definitions",sa.Column("id",sa.Integer(),primary_key=True,index=True),sa.Column("name",sa.String(100),nullable=False,unique=True),sa.Column("data_type",sa.String(20),nullable=False,server_default="text"),sa.Column("unit",sa.String(20)),sa.Column("options",sa.String(500)),sa.Column("sort_order",sa.Integer(),nullable=False,server_default="0"),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False))
    if "equipment_model_spec_values" not in tables: op.create_table("equipment_model_spec_values",sa.Column("id",sa.Integer(),primary_key=True,index=True),sa.Column("equipment_model_id",sa.Integer(),sa.ForeignKey("equipment_models.id",ondelete="CASCADE"),nullable=False,index=True),sa.Column("spec_definition_id",sa.Integer(),sa.ForeignKey("equipment_model_spec_definitions.id",ondelete="CASCADE"),nullable=False,index=True),sa.Column("value",sa.String(255),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint("equipment_model_id","spec_definition_id",name="uq_model_spec_value"))
def downgrade():
    bind=op.get_bind();tables=set(sa.inspect(bind).get_table_names())
    if "equipment_model_spec_values" in tables:op.drop_table("equipment_model_spec_values")
    if "equipment_model_spec_definitions" in tables:op.drop_table("equipment_model_spec_definitions")

