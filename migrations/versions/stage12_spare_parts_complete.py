"""Complete spare-parts movement lineage and correction support."""

from alembic import op
import sqlalchemy as sa

revision = "stage12_spare_parts_complete"
down_revision = "merge_spare_parts_heads_0034_receipt"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    doc_cols = {c["name"] for c in inspector.get_columns("spare_part_movement_documents")}
    item_cols = {c["name"] for c in inspector.get_columns("spare_part_movement_items")}

    with op.batch_alter_table("spare_part_movement_documents", schema=None) as batch:
        if "source_document_id" not in doc_cols:
            batch.add_column(
                sa.Column(
                    "source_document_id",
                    sa.Integer(),
                    # batch_alter_table() re-adds a column's ForeignKey as a
                    # standalone constraint and rejects unnamed ones with
                    # "ValueError: Constraint must have a name", which aborted
                    # startup on every existing database. This name is
                    # load-bearing -- do not drop it.
                    sa.ForeignKey(
                        "spare_part_movement_documents.id",
                        name="fk_spare_part_movement_documents_source_document_id",
                        ondelete="RESTRICT",
                    ),
                    nullable=True,
                )
            )
        if "updated_at" not in doc_cols:
            batch.add_column(
                sa.Column(
                    "updated_at",
                    sa.DateTime(),
                    nullable=False,
                    server_default=sa.text("CURRENT_TIMESTAMP"),
                )
            )
        batch.create_index(
            "ix_spare_part_movement_documents_source_document_id",
            ["source_document_id"],
            unique=False,
        )

    with op.batch_alter_table("spare_part_movement_items", schema=None) as batch:
        if "source_item_id" not in item_cols:
            batch.add_column(
                sa.Column(
                    "source_item_id",
                    sa.Integer(),
                    # named for the same reason as the one above
                    sa.ForeignKey(
                        "spare_part_movement_items.id",
                        name="fk_spare_part_movement_items_source_item_id",
                        ondelete="RESTRICT",
                    ),
                    nullable=True,
                )
            )
        batch.create_index(
            "ix_spare_part_movement_items_source_item_id",
            ["source_item_id"],
            unique=False,
        )
        batch.create_unique_constraint(
            "uq_spare_part_movement_document_source_item",
            ["document_id", "source_item_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("spare_part_movement_items", schema=None) as batch:
        batch.drop_constraint("uq_spare_part_movement_document_source_item", type_="unique")
        batch.drop_index("ix_spare_part_movement_items_source_item_id")
        batch.drop_column("source_item_id")

    with op.batch_alter_table("spare_part_movement_documents", schema=None) as batch:
        batch.drop_index("ix_spare_part_movement_documents_source_document_id")
        batch.drop_column("updated_at")
        batch.drop_column("source_document_id")
