"""Remove the unused closed fault status.

Revision ID: remove_closed_fault_status_20261013
Revises: merge_fault_repair_heads_20261013
"""

from alembic import op


revision = "remove_closed_fault_status_20261013"
down_revision = "merge_fault_repair_heads_20261013"
branch_labels = None
depends_on = None


def upgrade():
    # Preserve existing records by mapping the retired terminal status to the
    # supported completed status before tightening the database constraint.
    op.execute("UPDATE faults SET status = 'repaired' WHERE status = 'closed'")
    with op.batch_alter_table("faults") as batch_op:
        batch_op.drop_constraint("ck_fault_status", type_="check")
        batch_op.create_check_constraint(
            "ck_fault_status",
            "status IN ('open', 'diagnosing', 'repairing', 'waiting_parts', 'repaired')",
        )


def downgrade():
    with op.batch_alter_table("faults") as batch_op:
        batch_op.drop_constraint("ck_fault_status", type_="check")
        batch_op.create_check_constraint(
            "ck_fault_status",
            "status IN ('open', 'diagnosing', 'repairing', 'waiting_parts', 'repaired', 'closed')",
        )
