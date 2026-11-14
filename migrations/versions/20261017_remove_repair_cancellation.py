"""Remove cancellation as a repair status and reopen legacy cancelled repairs."""
from alembic import op
import sqlalchemy as sa


revision = "20261017_remove_repair_cancellation"
down_revision = "centralize_meter_values_only"
branch_labels = None
depends_on = None


_REPAIR_STATUS_CHECK = "ck_repair_status"


def _repairs_table_exists(bind) -> bool:
    return sa.inspect(bind).has_table("repairs")


def upgrade() -> None:
    bind = op.get_bind()
    if not _repairs_table_exists(bind):
        return

    conflicts = bind.execute(
        sa.text(
            "SELECT fault_id, COUNT(*) AS repair_count "
            "FROM repairs WHERE status IN ('in_progress', 'cancelled') "
            "GROUP BY fault_id HAVING COUNT(*) > 1"
        )
    ).fetchall()
    if conflicts:
        details = ", ".join(
            f"fault_id={row[0]} ({row[1]} repairs)" for row in conflicts
        )
        raise RuntimeError(
            "Cannot reopen cancelled repairs because an active repair already "
            f"exists for the same fault: {details}. Resolve these records "
            "explicitly, preserving repair history, then rerun the migration."
        )

    bind.execute(
        sa.text("UPDATE repairs SET status = 'in_progress' WHERE status = 'cancelled'")
    )
    constraints = {
        item.get("name")
        for item in sa.inspect(bind).get_check_constraints("repairs")
    }
    with op.batch_alter_table("repairs") as batch:
        if _REPAIR_STATUS_CHECK in constraints:
            batch.drop_constraint(_REPAIR_STATUS_CHECK, type_="check")
        batch.create_check_constraint(
            _REPAIR_STATUS_CHECK,
            "status IN ('in_progress', 'completed')",
        )


def downgrade() -> None:
    bind = op.get_bind()
    if not _repairs_table_exists(bind):
        return

    constraints = {
        item.get("name")
        for item in sa.inspect(bind).get_check_constraints("repairs")
    }
    with op.batch_alter_table("repairs") as batch:
        if _REPAIR_STATUS_CHECK in constraints:
            batch.drop_constraint(_REPAIR_STATUS_CHECK, type_="check")
        batch.create_check_constraint(
            _REPAIR_STATUS_CHECK,
            "status IN ('in_progress', 'completed', 'cancelled')",
        )
