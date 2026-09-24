"""merge equipment technical and brand migration heads

Revision ID: c8b492d2cb2f
Revises: 6b7f1c2d9e10, b7d3f1a9c5e2
"""

from typing import Sequence, Union


revision: str = "c8b492d2cb2f"
down_revision: Union[str, Sequence[str], None] = (
    "6b7f1c2d9e10",
    "b7d3f1a9c5e2",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
