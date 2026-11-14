"""Give a spare part request a single receipt date.

A request is received once, so its receipt date belongs to the request and not
to each line. The line column is left untouched — no data is destroyed — but
the request row becomes the date every line shares.

Existing rows are back-filled only when their lines already agree on one
date; a request whose lines disagree keeps a NULL date rather than having a
date invented for it, and is filled in explicitly afterwards.
"""

from alembic import op
import sqlalchemy as sa

revision = "receipt_date_rules"
down_revision = "drop_legacy_spare_part_name"
branch_labels = None
depends_on = None

TABLE = "spare_part_requests"
INDEX = "ix_spare_part_requests_received_date"


def _columns():
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(TABLE)}


def upgrade() -> None:
    if "received_date" not in _columns():
        with op.batch_alter_table(TABLE) as batch:
            batch.add_column(sa.Column("received_date", sa.Date(), nullable=True))
    op.create_index(INDEX, TABLE, ["received_date"], if_not_exists=True)

    op.execute(
        "UPDATE spare_part_requests SET received_date = ("
        "  SELECT MIN(i.received_date) FROM spare_part_request_items i"
        "  WHERE i.request_id = spare_part_requests.id AND i.received_date IS NOT NULL"
        ") WHERE received_date IS NULL AND ("
        "  SELECT COUNT(DISTINCT i.received_date) FROM spare_part_request_items i"
        "  WHERE i.request_id = spare_part_requests.id AND i.received_date IS NOT NULL"
        ") = 1"
    )


def downgrade() -> None:
    op.drop_index(INDEX, table_name=TABLE, if_exists=True)
    if "received_date" in _columns():
        with op.batch_alter_table(TABLE) as batch:
            batch.drop_column("received_date")
