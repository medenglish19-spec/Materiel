"""add maintenance_operation_models table

Stage 3 introduced the explicit operation↔model relation. This revision is the
single home of that relation's schema: the relation itself, and — since a
technical eligibility condition belongs to one model, not to the shared
operation — the per-model condition and warning columns.

Safety rules applied here on purpose:

* The legacy operation-level columns (`maintenance_operations.interval_*` and
  `warning_*`) are **never copied** into this table. A value that is valid for
  one model is not evidence about another model, and guessing was explicitly
  out of scope. Existing operations keep their values untouched until a real
  decision is made per model.
* A relation row is created with `condition_source = 'unset'`, meaning "no
  condition stored for this model yet". The application reports that state as
  «الشرط غير محدد» instead of falling back to the operation or to another model.
* `condition_source = 'model'` marks a condition that was configured for that
  model (its columns may still be empty on purpose, e.g. no active warning).
* Only columns are added on upgrade; no row is deleted or rewritten, so
  operation, plan and execution-record identifiers are preserved.
* `downgrade()` drops only the columns this revision added and keeps the
  relation table and its rows.

Revision ID: f5c253fe0ece
Revises: 20261009_remove_seeded_operation_description
Create Date: 2026-10-10 07:34:50.095575
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f5c253fe0ece'
down_revision: Union[str, Sequence[str], None] = '20261009_remove_seeded_operation_description'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "maintenance_operation_models"
MODEL_INDEX = "ix_maintenance_operation_models_equipment_model_id"

# (name, sa.Column) for every per-model condition column this revision adds.
_CONDITION_COLUMNS = (
    (
        "condition_source",
        sa.Column("condition_source", sa.String(length=20), nullable=False, server_default="unset"),
    ),
    ("interval_km", sa.Column("interval_km", sa.Numeric(10, 1), nullable=True)),
    ("interval_hours", sa.Column("interval_hours", sa.Numeric(10, 1), nullable=True)),
    ("interval_days", sa.Column("interval_days", sa.Integer(), nullable=True)),
    ("warning_km", sa.Column("warning_km", sa.Numeric(10, 1), nullable=True)),
    ("warning_days", sa.Column("warning_days", sa.Integer(), nullable=True)),
    (
        "is_active",
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    ),
)


def _inspector():
    return sa.inspect(op.get_bind())


def _has_table(name: str) -> bool:
    return name in set(_inspector().get_table_names())


def _column_names(table: str) -> set:
    return {column["name"] for column in _inspector().get_columns(table)}


def _index_names(table: str) -> set:
    return {index["name"] for index in _inspector().get_indexes(table)}


def upgrade() -> None:
    if not _has_table(TABLE):
        op.create_table(
            TABLE,
            sa.Column("operation_id", sa.Integer(), nullable=False),
            sa.Column("equipment_model_id", sa.Integer(), nullable=False),
            *[column for _, column in _CONDITION_COLUMNS],
            sa.ForeignKeyConstraint(
                ["operation_id"],
                ["maintenance_operations.id"],
                name="fk_maintenance_operation_models_operation",
                ondelete="CASCADE",
            ),
            sa.ForeignKeyConstraint(
                ["equipment_model_id"],
                ["equipment_models.id"],
                name="fk_maintenance_operation_models_equipment_model",
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("operation_id", "equipment_model_id", name="pk_maintenance_operation_models"),
        )
    else:
        # The relation table already exists (possibly from an earlier cut of
        # this revision). Add only what is missing; existing relationship rows
        # are preserved and stay at `condition_source = 'unset'`.
        existing = _column_names(TABLE)
        for name, column in _CONDITION_COLUMNS:
            if name not in existing:
                op.add_column(TABLE, column)

    if MODEL_INDEX not in _index_names(TABLE):
        op.create_index(MODEL_INDEX, TABLE, ["equipment_model_id"], unique=False)


def downgrade() -> None:
    if not _has_table(TABLE):
        return

    if MODEL_INDEX in _index_names(TABLE):
        op.drop_index(MODEL_INDEX, table_name=TABLE)

    # Keep the relation table and its rows: dropping it would delete every
    # operation↔model link, which is data, not schema.
    existing = _column_names(TABLE)
    for name, _ in reversed(_CONDITION_COLUMNS):
        if name in existing:
            op.drop_column(TABLE, name)
