import uuid

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


OLD_HEAD = "20261024_fuel_model_consumption_rates"
NEW_REVISION = "20261025_unify_asset_receiving"


def test_migration_routes_new_assets_through_request_items_and_preserves_rows(tmp_path):
    database = tmp_path / f"asset-request-receiving-{uuid.uuid4().hex}.db"
    url = "sqlite:///" + database.as_posix()
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("""
            CREATE TABLE spare_part_request_items (
                id INTEGER NOT NULL PRIMARY KEY,
                request_id INTEGER NOT NULL,
                part_name VARCHAR(200),
                requested_quantity NUMERIC(10, 2) NOT NULL,
                received_quantity NUMERIC(10, 2) NOT NULL DEFAULT 0
            )
        """))
        connection.execute(text("CREATE TABLE tires (id INTEGER NOT NULL PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE batteries (id INTEGER NOT NULL PRIMARY KEY)"))
        connection.execute(text("INSERT INTO spare_part_request_items (id, request_id, part_name, requested_quantity, received_quantity) VALUES (1, 1, 'إطار', 2, 2)"))
        connection.execute(text("INSERT INTO tires (id) VALUES (1)"))
        connection.execute(text("INSERT INTO batteries (id) VALUES (1)"))

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    command.stamp(config, OLD_HEAD)
    command.upgrade(config, NEW_REVISION)

    inspector = inspect(engine)
    item_columns = {column["name"] for column in inspector.get_columns("spare_part_request_items")}
    assert "asset_type" in item_columns
    assert "ck_spare_part_request_item_asset_type" in {
        check["name"] for check in inspector.get_check_constraints("spare_part_request_items")
    }
    for table in ("tires", "batteries"):
        assert "acquisition_request_item_id" in {
            column["name"] for column in inspector.get_columns(table)
        }
        assert f"fk_{table}_acquisition_request_item_id_spare_part_request_items" in {
            key["name"] for key in inspector.get_foreign_keys(table)
        }
    with engine.connect() as connection:
        assert connection.execute(text("SELECT asset_type FROM spare_part_request_items WHERE id=1")).scalar_one() == "part"
        connection.execute(text("UPDATE spare_part_request_items SET asset_type='tire' WHERE id=1"))
        connection.execute(text("UPDATE tires SET acquisition_request_item_id=1 WHERE id=1"))
        assert connection.execute(text("SELECT acquisition_request_item_id FROM tires WHERE id=1")).scalar_one() == 1

    command.downgrade(config, OLD_HEAD)
    inspector = inspect(engine)
    assert "asset_type" not in {column["name"] for column in inspector.get_columns("spare_part_request_items")}
    assert "acquisition_request_item_id" not in {column["name"] for column in inspector.get_columns("tires")}
    assert "acquisition_request_item_id" not in {column["name"] for column in inspector.get_columns("batteries")}
    with engine.connect() as connection:
        assert connection.execute(text("SELECT part_name FROM spare_part_request_items WHERE id=1")).scalar_one() == "إطار"
    engine.dispose()
