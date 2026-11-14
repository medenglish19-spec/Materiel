import importlib

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


def test_equipment_image_migration_preserves_existing_equipment(tmp_path):
    revision = importlib.import_module("migrations.versions.20261101_equipment_image")
    database = tmp_path / "equipment-image.db"
    url = "sqlite:///" + database.as_posix()
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE equipment (id INTEGER NOT NULL PRIMARY KEY, asset_code VARCHAR(50) NOT NULL)"))
        connection.execute(text("INSERT INTO equipment (id, asset_code) VALUES (1, 'EQ-OLD-1')"))
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": revision.down_revision},
        )

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url)
    command.upgrade(config, revision.revision)

    with engine.connect() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("equipment")}
        assert "image_url" in columns
        assert connection.execute(text("SELECT id, asset_code, image_url FROM equipment")).one() == (1, "EQ-OLD-1", None)

    command.downgrade(config, revision.down_revision)
    columns = {column["name"] for column in inspect(engine).get_columns("equipment")}
    assert "image_url" not in columns
    assert engine.connect().execute(text("SELECT count(*) FROM equipment")).scalar_one() == 1
    engine.dispose()
