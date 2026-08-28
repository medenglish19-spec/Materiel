"""baseline current Materiel schema

This revision intentionally contains no DDL. The existing application already
has a live schema and legacy repair code. On first migration bootstrap, the application
repairs that legacy schema, then stamps this revision. From this point onward, all
schema changes must be represented by new Alembic revisions.

Revision ID: 0001_baseline
Revises:
"""

from alembic import op


revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
