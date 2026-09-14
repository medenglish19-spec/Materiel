"""enforce tire movement timestamp integrity

revision: 0029
down_revision: 0028_tire_removal_disposition
"""
from alembic import op
import sqlalchemy as sa

revision = "0029_tire_movement_datetime_integrity"
down_revision = "0028_tire_removal_disposition"
branch_labels = None
depends_on = None


def _validate_existing_data():
    bind = op.get_bind()
    null_count = bind.execute(
        sa.text("SELECT COUNT(*) FROM tire_movements WHERE movement_datetime IS NULL")
    ).scalar()
    if null_count:
        raise RuntimeError(
            f"Cannot enforce NOT NULL on tire_movements.movement_datetime: {null_count} row(s) are missing a timestamp."
        )

    duplicates = bind.execute(
        sa.text(
            "SELECT tire_id, movement_datetime, COUNT(*) AS count "
            "FROM tire_movements "
            "GROUP BY tire_id, movement_datetime "
            "HAVING COUNT(*) > 1 LIMIT 5"
        )
    ).mappings().all()
    if duplicates:
        details = ", ".join(
            f"tire_id={row['tire_id']}, movement_datetime={row['movement_datetime']}, count={row['count']}"
            for row in duplicates
        )
        raise RuntimeError(
            "Cannot enforce unique tire movement timestamps because duplicate rows exist: " + details
        )


def upgrade():
    _validate_existing_data()
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("tire_movements", recreate="always") as batch_op:
            batch_op.drop_constraint("uq_tire_movement_identity", type_="unique")
            batch_op.alter_column(
                "movement_datetime",
                existing_type=sa.DateTime(),
                nullable=False,
            )
            batch_op.create_unique_constraint(
                "uq_tire_movement_timestamp", ["tire_id", "movement_datetime"]
            )
    else:
        op.drop_constraint("uq_tire_movement_identity", "tire_movements", type_="unique")
        op.alter_column(
            "tire_movements",
            "movement_datetime",
            existing_type=sa.DateTime(),
            nullable=False,
        )
        op.create_unique_constraint(
            "uq_tire_movement_timestamp", "tire_movements", ["tire_id", "movement_datetime"]
        )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        with op.batch_alter_table("tire_movements", recreate="always") as batch_op:
            batch_op.drop_constraint("uq_tire_movement_timestamp", type_="unique")
            batch_op.alter_column(
                "movement_datetime",
                existing_type=sa.DateTime(),
                nullable=True,
            )
            batch_op.create_unique_constraint(
                "uq_tire_movement_identity",
                ["equipment_id", "position_id", "movement_date", "id"],
            )
    else:
        op.drop_constraint("uq_tire_movement_timestamp", "tire_movements", type_="unique")
        op.alter_column(
            "tire_movements",
            "movement_datetime",
            existing_type=sa.DateTime(),
            nullable=True,
        )
        op.create_unique_constraint(
            "uq_tire_movement_identity",
            "tire_movements",
            ["equipment_id", "position_id", "movement_date", "id"],
        )
