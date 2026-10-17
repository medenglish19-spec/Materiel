from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from app.database import model_registry  # noqa: F401
from app.database.base import Base


OLD_HEAD = "20261018_tire_battery_asset_receipts"
CATALOG_TABLES = {
    "spare_part_categories",
    "spare_part_catalog_details",
    "spare_part_catalog_references",
    "spare_part_catalog_imports",
}


def test_catalog_migration_up_and_down_on_isolated_legacy_schema(tmp_path):
    database = tmp_path / "catalog-migration.db"
    url = "sqlite:///" + database.as_posix()
    engine = create_engine(url)
    legacy_tables = [table for table in Base.metadata.sorted_tables if table.name not in CATALOG_TABLES]
    Base.metadata.create_all(engine, tables=legacy_tables)
    with engine.begin() as connection:
        connection.execute(text("INSERT INTO spare_parts (part_number, name, receiving_document, notes) VALUES ('OLD-1', 'Existing part', 'receipt-1', NULL)"))

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    command.stamp(config, OLD_HEAD)
    command.upgrade(config, "head")

    inspector = inspect(engine)
    assert CATALOG_TABLES <= set(inspector.get_table_names())
    assert "uq_spare_part_catalog_details_spare_part_id" in {
        item["name"] for item in inspector.get_unique_constraints("spare_part_catalog_details")
    }
    foreign_keys = inspector.get_foreign_keys("spare_part_catalog_details")
    assert {item["name"] for item in foreign_keys} == {
        "fk_spare_part_catalog_details_spare_part_id",
        "fk_spare_part_catalog_details_category_id",
    }
    with engine.connect() as connection:
        row = connection.execute(text("SELECT part_number, receiving_document FROM spare_parts WHERE part_number='OLD-1'")).one()
        assert row == ("OLD-1", "receipt-1")

    command.downgrade(config, OLD_HEAD)
    assert not (CATALOG_TABLES & set(inspect(engine).get_table_names()))
    with engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM spare_parts WHERE part_number='OLD-1'")).scalar_one() == 1
    engine.dispose()
