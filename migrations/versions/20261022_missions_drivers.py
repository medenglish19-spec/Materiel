"""Add driver records and the shared driver-page column label setting."""
from alembic import op
import sqlalchemy as sa


revision = "20261022_missions_drivers"
down_revision = "20261021_spare_part_receiving_document_nullable"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "drivers",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_number", sa.String(50), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("center", sa.String(120), nullable=True),
        sa.Column("license_class", sa.String(50), nullable=False),
        sa.Column("license_issue_date", sa.Date(), nullable=True),
        sa.Column("license_expiry_date", sa.Date(), nullable=True),
        sa.Column("assigned_equipment_id", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.UniqueConstraint("employee_number", name="uq_drivers_employee_number"),
        sa.ForeignKeyConstraint(
            ["assigned_equipment_id"],
            ["equipment.id"],
            name="fk_drivers_assigned_equipment_id_equipment",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name="fk_drivers_created_by_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["users.id"],
            name="fk_drivers_updated_by_id_users",
        ),
    )
    op.create_index("ix_drivers_id", "drivers", ["id"])
    op.create_index(
        "ix_drivers_assigned_equipment_id", "drivers", ["assigned_equipment_id"]
    )

    with op.batch_alter_table("missions") as batch_op:
        batch_op.add_column(sa.Column("driver_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_missions_driver_id_drivers",
            "drivers",
            ["driver_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_missions_driver_id", ["driver_id"])

    op.create_table(
        "driver_system_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "center_column_label",
            sa.String(100),
            nullable=False,
            server_default="المركز",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name="fk_driver_system_settings_created_by_id_users",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"],
            ["users.id"],
            name="fk_driver_system_settings_updated_by_id_users",
        ),
    )


def downgrade():
    op.drop_table("driver_system_settings")
    with op.batch_alter_table("missions") as batch_op:
        batch_op.drop_index("ix_missions_driver_id")
        batch_op.drop_constraint("fk_missions_driver_id_drivers", type_="foreignkey")
        batch_op.drop_column("driver_id")
    op.drop_index("ix_drivers_assigned_equipment_id", table_name="drivers")
    op.drop_index("ix_drivers_id", table_name="drivers")
    op.drop_table("drivers")
