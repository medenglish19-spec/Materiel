"""Allow catalog parts to exist before a receiving document is available."""
from alembic import op
import sqlalchemy as sa


revision = "20261021_spare_part_receiving_document_nullable"
down_revision = "20261020_maintenance_catalog_imports"
branch_labels = None
depends_on = None


def _receiving_document_column():
    inspector = sa.inspect(op.get_bind())
    if "spare_parts" not in inspector.get_table_names():
        raise RuntimeError("Cannot update spare_parts: table does not exist")
    columns = {column["name"]: column for column in inspector.get_columns("spare_parts")}
    if "receiving_document" not in columns:
        raise RuntimeError("Cannot update spare_parts: receiving_document column does not exist")
    return columns["receiving_document"]


def _spare_parts_table(*, receiving_document_nullable):
    table = sa.Table(
        "spare_parts",
        sa.MetaData(),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("part_number", sa.String(80), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("receiving_document", sa.String(255), nullable=receiving_document_nullable),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.UniqueConstraint("part_number", name="uq_spare_part_number"),
    )
    sa.Index("ix_spare_parts_id", table.c.id)
    sa.Index("ix_spare_parts_part_number", table.c.part_number)
    return table


def _alter_nullability(nullable, *, existing_type, copy_from=None):
    options = {"copy_from": copy_from} if copy_from is not None else {}
    with op.batch_alter_table("spare_parts", **options) as batch_op:
        batch_op.alter_column(
            "receiving_document",
            existing_type=existing_type,
            nullable=nullable,
        )


def upgrade():
    if op.get_context().as_sql:
        _alter_nullability(
            True,
            existing_type=sa.String(255),
            copy_from=_spare_parts_table(receiving_document_nullable=True),
        )
        return

    column = _receiving_document_column()
    if column["nullable"]:
        return

    _alter_nullability(True, existing_type=column["type"])


def downgrade():
    if op.get_context().as_sql:
        _alter_nullability(
            False,
            existing_type=sa.String(255),
            copy_from=_spare_parts_table(receiving_document_nullable=False),
        )
        return

    column = _receiving_document_column()
    if not column["nullable"]:
        return

    null_count = op.get_bind().execute(
        sa.text("SELECT COUNT(*) FROM spare_parts WHERE receiving_document IS NULL")
    ).scalar_one()
    if null_count:
        raise RuntimeError(
            "Cannot restore receiving_document NOT NULL while spare parts have no receiving document"
        )

    _alter_nullability(False, existing_type=column["type"])
