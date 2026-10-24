"""Drop the obsolete operation-level interval constraint

The eligibility condition moved to the operation↔model relation
(`maintenance_operation_models`), so the operation row itself no longer carries
an effective interval. Keeping `ck_maintenance_operation_has_interval` in the
schema would forbid the state the architecture now requires: a general library
operation with no condition at all.

What this revision does:

* removes only that CHECK constraint; the legacy `interval_*` / `warning_*`
  columns and every value in them are preserved untouched;
* touches no diagnostic row, no plan, and no execution record;
* is a no-op on a database where the constraint is already absent.

SQLite cannot drop a CHECK constraint in place, so the table is rebuilt through
`batch_alter_table`. Every constraint of the rebuilt table is named explicitly,
and the rebuild is guarded so a database that has nothing to drop is never
rewritten.

Revision ID: a7d1c40f5b2e
Revises: f5c253fe0ece
Create Date: 2026-10-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7d1c40f5b2e"
down_revision: Union[str, Sequence[str], None] = "f5c253fe0ece"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "maintenance_operations"
CONSTRAINT = "ck_maintenance_operation_has_interval"


def _inspector():
    return sa.inspect(op.get_bind())


def _has_constraint() -> bool:
    if TABLE not in set(_inspector().get_table_names()):
        return False
    names = {constraint.get("name") for constraint in _inspector().get_check_constraints(TABLE)}
    return CONSTRAINT in names


def upgrade() -> None:
    if not _has_constraint():
        return
    with op.batch_alter_table(
        TABLE,
        schema=None,
        naming_convention={
            "pk": "pk_%(table_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
        },
    ) as batch_op:
        batch_op.drop_constraint(CONSTRAINT, type_="check")


def downgrade() -> None:
    # إعادة القيد ستمنع عملية بلا فاصل، وهي حالة مشروعة بعد نقل الشرط إلى
    # علاقة الطراز. لذلك لا يُعاد إنشاؤه، ولا تُحذف أي بيانات.
    pass
