"""Allow general spare-part requests with no fault or repair association."""

from alembic import op
import sqlalchemy as sa


revision = "20261104_spare_request_general_need"
down_revision = "20261102_user_credentials"
branch_labels = None
depends_on = None


_NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}

_SOURCE_TYPE = "source_type IN ('fault', 'repair', 'need')"
_SOURCE_MATCH = (
    "(source_type = 'fault' AND fault_id IS NOT NULL AND repair_id IS NULL) OR "
    "(source_type = 'repair' AND repair_id IS NOT NULL AND fault_id IS NULL) OR "
    "(source_type = 'need' AND fault_id IS NULL AND repair_id IS NULL AND equipment_id IS NULL)"
)


def upgrade():
    with op.batch_alter_table(
        "spare_part_requests", naming_convention=_NAMING_CONVENTION
    ) as batch_op:
        batch_op.drop_constraint("ck_spare_part_request_source_type", type_="check")
        batch_op.drop_constraint("ck_spare_part_request_source_match", type_="check")
        batch_op.create_check_constraint(
            "ck_spare_part_request_source_type", _SOURCE_TYPE
        )
        batch_op.create_check_constraint(
            "ck_spare_part_request_source_match", _SOURCE_MATCH
        )


def downgrade():
    bind = op.get_bind()
    if bind.execute(
        sa.text("SELECT COUNT(*) FROM spare_part_requests WHERE source_type = 'need'")
    ).scalar_one():
        raise RuntimeError(
            "Cannot downgrade while general need requests exist; export or reclassify them first."
        )
    with op.batch_alter_table(
        "spare_part_requests", naming_convention=_NAMING_CONVENTION
    ) as batch_op:
        batch_op.drop_constraint("ck_spare_part_request_source_type", type_="check")
        batch_op.drop_constraint("ck_spare_part_request_source_match", type_="check")
        batch_op.create_check_constraint(
            "ck_spare_part_request_source_type", "source_type IN ('fault', 'repair')"
        )
        batch_op.create_check_constraint(
            "ck_spare_part_request_source_match",
            "(source_type = 'fault' AND fault_id IS NOT NULL AND repair_id IS NULL) OR "
            "(source_type = 'repair' AND repair_id IS NOT NULL AND fault_id IS NULL)",
        )
