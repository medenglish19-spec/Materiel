"""Merge the spare-parts redesign and technical-spec cleanup migration heads."""

from typing import Sequence, Union

from alembic import op


revision: str = "merge_stage11_c3a9e7f21d04"
down_revision: Union[str, Sequence[str], None] = (
    "stage11_spare_part_requests_redesign",
    "c3a9e7f21d04",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
