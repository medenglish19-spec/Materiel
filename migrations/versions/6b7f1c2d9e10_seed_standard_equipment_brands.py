"""seed standard equipment brands

Revision ID: 6b7f1c2d9e10
Revises: da62b4ffe6fd
Create Date: 2026-09-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "6b7f1c2d9e10"
down_revision: Union[str, Sequence[str], None] = "da62b4ffe6fd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


DEFAULT_BRANDS = (
    "Toyota",
    "Nissan",
    "Mitsubishi",
    "Isuzu",
    "Mercedes-Benz",
    "MAN",
    "Volvo",
    "Scania",
    "Hyundai",
    "Ford",
    "Caterpillar",
    "Komatsu",
)


def upgrade() -> None:
    bind = op.get_bind()
    brands = sa.table(
        "equipment_brands",
        sa.column("name", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    for name in DEFAULT_BRANDS:
        exists = bind.execute(
            sa.select(brands.c.name).where(brands.c.name == name).limit(1)
        ).first()
        if exists is None:
            bind.execute(
                brands.insert().values(name=name, is_active=True, created_at=sa.func.current_timestamp(), updated_at=sa.func.current_timestamp())
            )


def downgrade() -> None:
    bind = op.get_bind()
    brands = sa.table(
        "equipment_brands",
        sa.column("name", sa.String),
    )
    bind.execute(
        brands.delete().where(brands.c.name.in_(DEFAULT_BRANDS))
    )
