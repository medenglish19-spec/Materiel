"""Compatibility shim for the deleted `free_text_spare_part_names` revision.

An earlier attempt at this change shipped a revision under this identifier and
some databases were stamped with it; the file was then removed, which left
`alembic upgrade` unable to resolve the stored version and the application
unable to start. This revision exists only so that stamp resolves again and
the chain can walk forward to `spare_part_request_item_free_name`, which does
the actual column work.

Its body is intentionally empty: a database already stamped here never runs
it, and a fresh database has no legacy column to normalize.
"""

from alembic import op  # noqa: F401

revision = "free_text_spare_part_names"
down_revision = "add_received_date_spare_part_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
