spare_parts_movements: what the balances feature is and why it looks like this

The balances feature (استلام ← توزيع ← إرجاع ← الرصيد) is now implemented and
tested, but **not committed** — it is still sitting in the working tree as three
modified files plus one new test file:

- app/modules/spare_parts_movements/services.py
- app/modules/spare_parts_requests/services.py
- app/modules/spare_parts_requests/templates/received.html
- tests/test_spare_part_movement_balances.py   (new, untracked)

`git diff` is the review surface for all of it.

## `aliased()` in `_returned_total_for_request_item` is load-bearing

The join targets the same table twice: the return item, and the distribution it
corrects. Importing the class under a second name is not an alias, so SQLAlchemy
emitted

    FROM spare_part_movement_items
    JOIN spare_part_movement_documents ON ...
    JOIN spare_part_movement_items
      ON spare_part_movement_items.source_item_id = spare_part_movement_items.id

and SQLite rejected it with `ambiguous column name:
spare_part_movement_items.quantity` — the column exists on both sides of an
unaliased self-join. `DistItem = aliased(SparePartMovementItem)` is what makes it
run. Without it, `tests/test_spare_parts_inline_edit.py` fails 2 tests and
`tests/test_spare_part_receipt_dates.py` fails 1.

The duplicate definition that used to sit above it (ending in `pass`, carrying an
`if False else True` self-join) is gone. That was dead code: the second
definition shadowed the first at import time, so it could never run.

## Two decisions worth a reviewer's eye

**The state is derived, most specific first.** `_status()` has no precedence
table and no manual status field. When two states match the same balances it
returns the more specific one: received 10, distributed 3, returned 1 satisfies
both "partially distributed" and "part remaining with the entity", and the second
wins because it mentions the return. Ordering it the other way is a one-line
change in `_status()` and `test_the_most_specific_state_wins_when_two_overlap`
is the test that pins it.

**`available_for_distribution` reads `available_quantity()`, not
`received - distributed`.** The register and the distribution page then cannot
disagree about the same item. The two formulas differ only when a legacy return
exists — a return row with no `source_item_id`, which predates the link to a
distribution document and which `create_document()` cannot create any more. Those
rows are in the live database, and they correctly put the piece back into stock,
so `available_quantity()` subtracts them. `remaining_with_entity` deliberately
does **not** use them: a legacy return is not something the recipient sent back.

## The quantity guard is in the service, not only the schema

`MovementItemCreate.quantity` was already `Field(gt=0)`, so a zero or negative
quantity used to die in pydantic. That is not the same as the service refusing
it: a payload that reaches `create_document()` without passing the schema would
have gone through. `_quantity()` now rejects zero, negative, and fractional in
`_distribution_line` and `_return_line`, which covers create and update alike.
`test_a_zero_or_negative_distribution_is_refused` builds its payload with
`model_construct` specifically so it does not pass through pydantic and cannot
pass for the schema's sake.

## Also new since the branch started

- stage13 and stage14 applied to fleet_assets.db, and SQLite foreign key
  enforcement is now on for every connection. That means a write naming a deleted
  parent will now raise IntegrityError instead of being stored. The live database
  is clean (check_db_health.py reports no problems), and the full suite passes
  with enforcement on, but if any code path deliberately wrote a dangling
  reference it will now fail loudly rather than quietly.