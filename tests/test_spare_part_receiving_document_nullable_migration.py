import uuid

import pytest
import sqlalchemy as sa
from alembic import command, op
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app.database import model_registry  # noqa: F401
from app.database.base import Base
from app.modules.spare_parts_catalog.router import _make_part


OLD_HEAD = "20261018_tire_battery_asset_receipts"
NEW_REVISION = "20261021_spare_part_receiving_document_nullable"
CATALOG_TABLES = {
    "spare_part_categories",
    "spare_part_catalog_details",
    "spare_part_catalog_references",
    "spare_part_catalog_imports",
    "maintenance_catalog_imports",
}


def _legacy_database(tmp_path):
    database = tmp_path / f"spare-parts-nullability-{uuid.uuid4().hex}.db"
    engine = create_engine(f"sqlite:///{database}")
    legacy_tables = [table for table in Base.metadata.sorted_tables if table.name not in CATALOG_TABLES]
    Base.metadata.create_all(engine, tables=legacy_tables)

    # Reproduce operational databases whose receiving_document was created NOT NULL.
    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            with op.batch_alter_table("spare_parts") as batch_op:
                batch_op.alter_column(
                    "receiving_document",
                    existing_type=sa.String(255),
                    nullable=False,
                )
        connection.execute(
            text(
                "INSERT INTO spare_parts (part_number, name, receiving_document, notes) "
                "VALUES ('OLD-1', 'Existing part', 'receipt-1', NULL)"
            )
        )

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database.as_posix()}")
    command.stamp(config, OLD_HEAD)
    engine.dispose()
    return database, config


def test_migration_allows_missing_receiving_document_and_preserves_history(tmp_path):
    database, config = _legacy_database(tmp_path)

    command.upgrade(config, NEW_REVISION)

    engine = create_engine(f"sqlite:///{database}")
    receiving_document = next(
        column for column in inspect(engine).get_columns("spare_parts")
        if column["name"] == "receiving_document"
    )
    assert receiving_document["nullable"] is True
    with Session(engine) as session:
        part = _make_part(
            session,
            name="Catalog part",
            name_ar="قطعة كتالوج",
            name_fr="",
            reference="TEST-REF-1",
            manufacturer="QA",
            category="",
            notes="created after schema repair",
            source="migration test",
        )
        catalog_part_number = part.part_number
        session.commit()
        assert part.receiving_document is None
    with engine.begin() as connection:
        assert connection.execute(
            text("SELECT part_number, receiving_document FROM spare_parts WHERE part_number='OLD-1'")
        ).one() == ("OLD-1", "receipt-1")
        assert connection.execute(
            text("SELECT receiving_document FROM spare_parts WHERE part_number=:part_number"),
            {"part_number": catalog_part_number},
        ).scalar_one() is None
        connection.execute(text("DELETE FROM spare_parts WHERE part_number=:part_number"), {"part_number": catalog_part_number})
    engine.dispose()

    command.downgrade(config, OLD_HEAD)

    engine = create_engine(f"sqlite:///{database}")
    receiving_document = next(
        column for column in inspect(engine).get_columns("spare_parts")
        if column["name"] == "receiving_document"
    )
    assert receiving_document["nullable"] is False
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT part_number, receiving_document FROM spare_parts WHERE part_number='OLD-1'")
        ).one() == ("OLD-1", "receipt-1")
    engine.dispose()


def test_downgrade_refuses_to_drop_nullability_when_catalog_parts_need_it(tmp_path):
    database, config = _legacy_database(tmp_path)
    command.upgrade(config, NEW_REVISION)

    engine = create_engine(f"sqlite:///{database}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO spare_parts (part_number, name, receiving_document, notes) "
                "VALUES ('CAT-1', 'Catalog part', NULL, NULL)"
            )
        )
    engine.dispose()

    with pytest.raises(RuntimeError, match="Cannot restore receiving_document NOT NULL"):
        command.downgrade(config, OLD_HEAD)

    engine = create_engine(f"sqlite:///{database}")
    receiving_document = next(
        column for column in inspect(engine).get_columns("spare_parts")
        if column["name"] == "receiving_document"
    )
    assert receiving_document["nullable"] is True
    with engine.connect() as connection:
        assert connection.execute(
            text("SELECT part_number FROM spare_parts WHERE part_number='CAT-1'")
        ).scalar_one() == "CAT-1"
    engine.dispose()
