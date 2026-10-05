"""The spare-parts movement migration has to run against an existing database.

``stage12_spare_parts_complete`` adds lineage columns with batch_alter_table().
On a brand-new database it never runs at all -- init_db() does create_all() and
stamps head -- so the only place it can break is a database that already exists.
It did: batch mode re-adds a column's ForeignKey as a standalone constraint and
rejects unnamed ones, so startup died with "ValueError: Constraint must have a
name" on every existing install while a fresh one looked perfectly healthy.

These tests build the older shape of the two tables on purpose and migrate it.

NOTE: migrations/env.py deliberately migrates ``settings.DATABASE_URL`` and
ignores ``Config.set_main_option("sqlalchemy.url", ...)``. So the only way to
aim a migration at a scratch file is to point settings at it, which is what
``_migrate`` does. Getting that wrong writes to the real database.
"""

import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MERGE = "merge_spare_parts_heads_0034_receipt"
STAGE12 = "stage12_spare_parts_complete"

# The tables as they existed before stage12: no lineage columns, no source
# indexes. This is the shape every existing database is sitting in.
OLD_DOCUMENTS = """
CREATE TABLE spare_part_movement_documents (
    id INTEGER NOT NULL,
    document_number VARCHAR(80) NOT NULL,
    document_type VARCHAR(20) NOT NULL,
    document_date DATE NOT NULL,
    issuer VARCHAR(160) NOT NULL,
    recipient VARCHAR(160) NOT NULL,
    beneficiary VARCHAR(200),
    notes TEXT,
    created_by_id INTEGER,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_spare_part_movement_document_type
        CHECK (document_type IN ('distribution', 'return')),
    CONSTRAINT uq_spare_part_movement_document_number UNIQUE (document_number),
    FOREIGN KEY(created_by_id) REFERENCES users (id) ON DELETE SET NULL
)
"""

OLD_ITEMS = """
CREATE TABLE spare_part_movement_items (
    id INTEGER NOT NULL,
    document_id INTEGER NOT NULL,
    request_item_id INTEGER NOT NULL,
    quantity NUMERIC NOT NULL,
    notes TEXT,
    PRIMARY KEY (id),
    CONSTRAINT ck_spare_part_movement_item_quantity_positive CHECK (quantity > 0),
    CONSTRAINT uq_spare_part_movement_document_item UNIQUE (document_id, request_item_id),
    FOREIGN KEY(document_id) REFERENCES spare_part_movement_documents (id) ON DELETE CASCADE,
    FOREIGN KEY(request_item_id) REFERENCES spare_part_request_items (id) ON DELETE RESTRICT
)
"""


def _existing_database(path: Path) -> Path:
    """A database stamped at the merge revision, with pre-stage12 movement tables."""
    con = sqlite3.connect(path)
    try:
        # the two tables the movement tables point at; batch mode resolves the
        # foreign keys while it rebuilds, so they have to exist
        con.execute("CREATE TABLE users (id INTEGER NOT NULL, PRIMARY KEY (id))")
        con.execute("CREATE TABLE spare_part_request_items ("
                    "id INTEGER NOT NULL, PRIMARY KEY (id))")
        con.execute(OLD_DOCUMENTS)
        con.execute(OLD_ITEMS)
        con.execute("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)")
        con.execute("INSERT INTO alembic_version VALUES (?)", (MERGE,))
        con.commit()
    finally:
        con.close()
    return path


def _migrate(path: Path):
    from alembic import command
    from alembic.config import Config

    from app.core.config import settings
    from app.database import model_registry  # noqa: F401

    previous = settings.DATABASE_URL
    settings.DATABASE_URL = f"sqlite:///{path.as_posix()}"
    try:
        config = Config(str(ROOT / "alembic.ini"))
        return command.upgrade(config, "head")
    finally:
        settings.DATABASE_URL = previous


def _columns(path: Path, table: str) -> set[str]:
    con = sqlite3.connect(path)
    try:
        return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
    finally:
        con.close()


def _ddl(path: Path, table: str) -> str:
    con = sqlite3.connect(path)
    try:
        row = con.execute(
            "SELECT sql FROM sqlite_master WHERE name=?", (table,)
        ).fetchone()
        return row[0] if row else ""
    finally:
        con.close()


def test_stage12_runs_on_an_existing_database(tmp_path):
    """The exact failure that stopped the app: batch mode, unnamed FK."""
    db = _existing_database(tmp_path / "existing.db")

    _migrate(db)  # used to raise ValueError("Constraint must have a name")

    from alembic.config import Config
    from alembic.script import ScriptDirectory

    scripts = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    head = scripts.get_current_head()
    assert STAGE12 in {r.revision for r in scripts.walk_revisions()}, (
        "stage12 is no longer in the migration history"
    )

    con = sqlite3.connect(db)
    try:
        stamp = con.execute("SELECT version_num FROM alembic_version").fetchone()[0]
        assert stamp == head, (
            f"the migration did not run to head: {stamp} != {head}"
        )
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        con.close()


def test_a_failed_migration_leaves_nothing_behind(tmp_path):
    """A half-applied batch leaves _alembic_tmp_ tables that block the retry."""
    db = _existing_database(tmp_path / "existing.db")
    _migrate(db)

    con = sqlite3.connect(db)
    try:
        leftovers = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE name LIKE '%_alembic_tmp%'")]
        assert not leftovers, f"stray temp tables will break the next run: {leftovers}"
    finally:
        con.close()


def test_stage12_adds_everything_it_promises(tmp_path):
    db = _existing_database(tmp_path / "existing.db")
    _migrate(db)

    docs = _columns(db, "spare_part_movement_documents")
    items = _columns(db, "spare_part_movement_items")

    assert {"source_document_id", "updated_at"} <= docs, docs
    assert "source_item_id" in items, items


def test_stage12_keeps_the_columns_it_added_on_a_second_run(tmp_path):
    """The migration guards on existing columns, so re-running it must be safe."""
    db = _existing_database(tmp_path / "existing.db")
    _migrate(db)
    before = _columns(db, "spare_part_movement_documents")

    _migrate(db)

    assert _columns(db, "spare_part_movement_documents") == before


def test_the_new_foreign_keys_are_named_in_the_schema(tmp_path):
    """Unnamed ones are what batch mode refuses; keep them named in the schema."""
    db = _existing_database(tmp_path / "existing.db")
    _migrate(db)

    ddl = _ddl(db, "spare_part_movement_documents")
    assert "fk_spare_part_movement_documents_source_document_id" in ddl, ddl


@pytest.mark.parametrize("target,expected_name", [
    ("spare_part_movement_documents.id",
     "fk_spare_part_movement_documents_source_document_id"),
    ("spare_part_movement_items.id",
     "fk_spare_part_movement_items_source_item_id"),
])
def test_every_foreign_key_the_migration_adds_is_named(target, expected_name):
    """Read the migration itself: no ForeignKey may go in without a name."""
    import ast

    source = ROOT / "migrations" / "versions" / "stage12_spare_parts_complete.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))

    declared = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, "attr", None) != "ForeignKey" or not node.args:
            continue
        referred = getattr(node.args[0], "value", None)
        keywords = {k.arg: getattr(k.value, "value", None) for k in node.keywords}
        if referred:
            declared[referred] = keywords.get("name")

    assert target in declared, f"{target} is not declared by the migration: {declared}"
    assert declared[target] == expected_name, (
        f"{target} has name={declared[target]!r}; batch_alter_table refuses unnamed "
        f"constraints, so this must stay {expected_name!r}"
    )