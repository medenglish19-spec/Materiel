"""add technician and note to maintenance records

Revision ID: d4a91c7e2f60
Revises: 3bee137f2e96
Create Date: 2026-10-11

إضافة حقلين اختياريين إلى `maintenance_records` لدعم شاشة «تسجيل صيانة جديدة»:

* `technician_id` — مرجع إلى «الفني المنفذ» من جدول الفنيين الفعلي
  (`workshop_technicians`)، مع `ON DELETE SET NULL` حتى لا يمنع حذف فنيّ
  الاحتفاظ بالسجل التاريخي.
* `note` — «الملاحظة»، نصّ إضافي منفصل عن «الأعمال المنجزة» (`description`).

كلا العمودين `nullable=True`، فلا يتأثر أي صف موجود، ولا يُحذف أي بيانات.
الترحيل محميّ بحيث لا يفشل إن سبق تطبيق جزء منه يدويًا.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4a91c7e2f60"
down_revision: Union[str, Sequence[str], None] = "3bee137f2e96"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "maintenance_records"
_FK_NAME = "fk_maintenance_records_technician_id"
_IX_NAME = "ix_maintenance_records_technician_id"


def _columns(bind, table):
    return {column["name"] for column in sa.inspect(bind).get_columns(table)}


def _indexes(bind, table):
    return {index["name"] for index in sa.inspect(bind).get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return

    columns = _columns(bind, _TABLE)
    indexes = _indexes(bind, _TABLE)

    with op.batch_alter_table(_TABLE, schema=None) as batch_op:
        if "technician_id" not in columns:
            batch_op.add_column(sa.Column("technician_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                _FK_NAME,
                "workshop_technicians",
                ["technician_id"],
                ["id"],
                ondelete="SET NULL",
            )
        if _IX_NAME not in indexes:
            batch_op.create_index(_IX_NAME, ["technician_id"], unique=False)
        if "note" not in columns:
            batch_op.add_column(sa.Column("note", sa.Text(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if _TABLE not in inspector.get_table_names():
        return

    columns = _columns(bind, _TABLE)
    indexes = _indexes(bind, _TABLE)

    with op.batch_alter_table(_TABLE, schema=None) as batch_op:
        if _IX_NAME in indexes:
            batch_op.drop_index(_IX_NAME)
        if "technician_id" in columns:
            batch_op.drop_constraint(_FK_NAME, type_="foreignkey")
            batch_op.drop_column("technician_id")
        if "note" in columns:
            batch_op.drop_column("note")
