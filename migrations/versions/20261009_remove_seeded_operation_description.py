"""Remove the seeded default description from library operations.

The stage9 seed wrote the same long default description onto every seeded
maintenance operation, so the rules library table showed the identical text
under nearly every name. Drop that exact value from `maintenance_operations`
now that the library is editable; operations keep any real customized
description.

Revision ID: 20261009_remove_seeded_operation_description
Revises: 20261009_maintenance_plan_approval
"""
from alembic import op
import sqlalchemy as sa

revision = "20261009_remove_seeded_operation_description"
down_revision = "20261009_maintenance_plan_approval"
branch_labels = None
depends_on = None

SEEDED_DESCRIPTION = (
    "عملية قياسية قابلة للتعديل؛ يحدد الفاصل النهائي "
    "حسب دليل الشركة المصنعة والطراز وظروف التشغيل."
)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "maintenance_operations" not in tables:
        return
    columns = {column["name"] for column in inspector.get_columns("maintenance_operations")}
    if "description" not in columns:
        return
    op.execute(
        sa.text(
            "UPDATE maintenance_operations SET description = NULL "
            "WHERE description = :seeded"
        ).bindparams(seeded=SEEDED_DESCRIPTION)
    )


def downgrade() -> None:
    # The seeded description is treated as removable library data; there is no
    # reliable way to tell which rows carried the seed versus a real edit, so
    # the reverse operation intentionally does nothing (same policy as stage9).
    pass
