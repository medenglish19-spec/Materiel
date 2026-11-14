"""Merge the two spare-parts migration heads.

Two branches grew out of ``add_received_date_spare_part_items`` at the same
time:

* ``0034_spare_part_distribution_return`` -- distribution/return documents,
* ``free_text_spare_part_names -> spare_part_request_item_free_name ->
  drop_legacy_spare_part_name -> receipt_date_rules`` -- one receipt date per
  request.

A repository with two heads cannot migrate at all. Both ``command.stamp`` and
``command.upgrade(config, "head")`` refuse with "Multiple heads are present",
so ``init_db()`` raises on every startup and ``run_web.py`` exits before it
serves anything. That is what broke the run_web smoke test.

The branches touch disjoint objects -- ``0034`` creates the two
``spare_part_movement_*`` tables, ``receipt_date_rules`` adds
``spare_part_requests.received_date`` and its index -- so merging needs no
data of its own.

revision id: merge_spare_parts_heads_0034_receipt
Revises: 0034_spare_part_distribution_return, receipt_date_rules
"""

from typing import Sequence, Union


revision: str = "merge_spare_parts_heads_0034_receipt"
down_revision: Union[str, Sequence[str], None] = (
    "0034_spare_part_distribution_return",
    "receipt_date_rules",
)
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
