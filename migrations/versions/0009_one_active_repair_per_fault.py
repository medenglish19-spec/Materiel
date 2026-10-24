"""Enforce at most one active repair per fault.

Historical completed and cancelled repairs are intentionally unrestricted.
The migration refuses to continue if legacy duplicate active rows exist, rather
than silently deleting or rewriting repair history.
"""
from alembic import op
import sqlalchemy as sa


revision = "0009_one_active_repair_per_fault"
down_revision = ("0011_fault_exploitation_impact", "d4a91c7e2f60")
branch_labels = None
depends_on = None

INDEX_NAME = "uq_repairs_one_active_per_fault"


def upgrade() -> None:
    bind = op.get_bind()
    # Some migration-focused tests and partial legacy schemas intentionally do
    # not contain the faults/repairs tables yet. This revision is a merge point;
    # skip the constraint until the repairs table exists.
    if not sa.inspect(bind).has_table("repairs"):
        return

    dialect = bind.dialect.name
    if dialect not in {"sqlite", "postgresql"}:
        raise RuntimeError(
            "The one-active-repair constraint requires SQLite or PostgreSQL "
            "partial unique indexes."
        )

    duplicates = bind.execute(
        sa.text(
            "SELECT fault_id, COUNT(*) AS active_count "
            "FROM repairs WHERE status = 'in_progress' "
            "GROUP BY fault_id HAVING COUNT(*) > 1"
        )
    ).fetchall()
    if duplicates:
        details = ", ".join(
            f"fault_id={row[0]} ({row[1]} active rows)" for row in duplicates
        )
        raise RuntimeError(
            "Cannot enforce one active repair per fault because duplicate "
            f"active repair rows already exist: {details}. Resolve these "
            "records explicitly, preserving repair history, then rerun the migration."
        )

    predicate = sa.text("status = 'in_progress'")
    op.create_index(
        INDEX_NAME,
        "repairs",
        ["fault_id"],
        unique=True,
        sqlite_where=predicate,
        postgresql_where=predicate,
    )


def downgrade() -> None:
    bind = op.get_bind()
    if sa.inspect(bind).has_table("repairs"):
        indexes = {item["name"] for item in sa.inspect(bind).get_indexes("repairs")}
        if INDEX_NAME in indexes:
            op.drop_index(INDEX_NAME, table_name="repairs")
