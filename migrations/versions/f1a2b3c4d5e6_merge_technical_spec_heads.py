"""merge technical specification migration heads

Revision ID: f1a2b3c4d5e6
Revises: 0033_complete_technical_taxonomy, da62b4ffe6fd
"""

from typing import Sequence, Union


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = (
    "0033_complete_technical_taxonomy",
    "da62b4ffe6fd",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
