"""clear select option list copied into spec unit

Legacy seed migrations unpacked the 5th element of the spec tuple into ``unit``,
but for ``select`` rows that element holds the option list. Every select
definition therefore stored the full option list inside ``unit``, and templates
that append ``spec.definition.unit`` rendered e.g.
``حافلة بيك أب,سيدان,دفع رباعي,شاحنة,حافلة,خاص`` after the selected value.

This only clears ``unit`` where the corruption is provable (``unit`` is exactly
the ``options`` list). Any other ``unit`` value is left untouched rather than
guessed at, and non-select definitions keep their real units (mm, kg, Ah, ...).

Revision ID: c3a9e7f21d04
Revises: 5c68afc7b0d3
Create Date: 2026-10-01 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'c3a9e7f21d04'
down_revision: Union[str, Sequence[str], None] = '5c68afc7b0d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE equipment_model_spec_definitions
           SET unit = NULL
         WHERE data_type = 'select'
           AND unit IS NOT NULL
           AND unit = options
        """
    )


def downgrade() -> None:
    # The cleared values were a copy of `options`, so they are recoverable in
    # principle but restoring them would reintroduce the rendering bug.
    pass
