"""Merge the active-repair constraint and repair date migration heads.

This is a graph-only merge. Both parent migrations remain independently
reversible, and no application data is changed by this revision.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "merge_fault_repair_heads_20261013"
down_revision: Union[str, Sequence[str], None] = (
    "0009_one_active_repair_per_fault",
    "0053_repair_start_end_dates",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
