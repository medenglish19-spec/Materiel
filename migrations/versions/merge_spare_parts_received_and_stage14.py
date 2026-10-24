"""Merge the spare-parts received-date and stage14 migration heads."""

from typing import Sequence, Union

from alembic import op


revision: str = "merge_spare_parts_received_stage14"
down_revision: Union[str, Sequence[str], None] = (
    "add_received_date_spare_part_items",
    "stage14_null_orphaned_spec_categories",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
