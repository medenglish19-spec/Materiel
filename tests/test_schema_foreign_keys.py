"""Two ways this project has already been bitten by unnamed foreign keys.

In batch mode (``batch_alter_table``) Alembic rebuilds the table by copying it,
and an unnamed constraint cannot be copied -- SQLAlchemy raises "ValueError:
Constraint must have a name". ``stage12_spare_parts_complete`` hit exactly that,
which stopped the app from starting on every database that already existed while
fresh installs looked fine. So a migration that rebuilds a table has to name
every foreign key it introduces.

The other direction is a model pointing at a table that does not exist. Nothing
fails at import; the error surfaces much later, from wherever the schema is
first reflected or created.
"""

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

VERSIONS = ROOT / "migrations" / "versions"

BATCH = "batch_alter_table"


def _foreign_keys(tree: ast.AST) -> list[tuple[str, str | None]]:
    """Every sa.ForeignKey(...) in a file, as (referred table, name)."""
    declared = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, "attr", None) != "ForeignKey" or not node.args:
            continue
        referred = getattr(node.args[0], "value", None)
        if not referred:
            continue
        names = {
            kw.arg: getattr(kw.value, "value", None)
            for kw in node.keywords
            if kw.arg == "name"
        }
        declared.append((referred, names.get("name")))
    return declared


def _rebuilds_tables(source: str) -> bool:
    return BATCH in source


def _batch_migrations() -> list[Path]:
    return [
        path
        for path in sorted(VERSIONS.glob("*.py"))
        if _rebuilds_tables(path.read_text(encoding="utf-8"))
    ]


def test_some_migration_rebuilds_a_table():
    """Otherwise the check below would pass by finding nothing."""
    assert _batch_migrations(), (
        f"no migration under {VERSIONS.name} uses {BATCH}() any more -- if that is "
        "deliberate, drop the naming rule; do not let it go quiet"
    )


def test_the_naming_rule_actually_has_something_to_check():
    """Most batch migrations add no foreign key; some do, and those are the risk."""
    adds_a_key = [
        path.stem
        for path in _batch_migrations()
        if _foreign_keys(ast.parse(path.read_text(encoding="utf-8")))
    ]
    assert adds_a_key, (
        "no batch migration adds a foreign key any more, so the naming rule below "
        "checks nothing -- if that is deliberate, delete it rather than leave it green"
    )


@pytest.mark.parametrize(
    "path", _batch_migrations(), ids=lambda p: p.stem
)
def test_a_migration_that_rebuilds_a_table_names_every_foreign_key(path):
    for referred, name in _foreign_keys(ast.parse(path.read_text(encoding="utf-8"))):
        assert name, (
            f"{path.stem} adds ForeignKey({referred!r}) with no name, but it "
            f"rebuilds a table with {BATCH}() -- copying an unnamed constraint "
            'raises "ValueError: Constraint must have a name" and the migration '
            "aborts partway, leaving tables that block the retry"
        )


def test_every_foreign_key_points_at_a_table_that_exists():
    """A model referencing a table that was never imported fails very late."""
    from app.database import model_registry  # noqa: F401
    from app.database.base import Base

    known = set(Base.metadata.tables)
    assert known, "no tables in the metadata -- model_registry was not imported"

    checked = 0
    for name, table in Base.metadata.tables.items():
        for fk in table.foreign_keys:
            target = fk.column.table.name
            checked += 1
            assert target in known, (
                f"{name}.{fk.parent.name} has a ForeignKey to {target!r}, which is "
                "not in the metadata -- either that model was never imported or the "
                "table name is wrong, and nothing will notice until a schema is built"
            )

    assert checked, "the metadata declares no foreign keys at all -- did it load?"


def test_every_foreign_key_in_the_models_is_named():
    """create_all() must produce the same names the migrations write."""
    from app.database import model_registry  # noqa: F401
    from app.database.base import Base

    unnamed, checked = [], 0
    for table_name, table in Base.metadata.tables.items():
        for fkc in table.foreign_key_constraints:
            checked += 1
            if not fkc.name:
                unnamed.append(f"{table_name}({', '.join(sorted(fkc.columns))})")

    assert checked, "no foreign keys in the metadata -- did model_registry load?"
    assert not unnamed, (
        f"{len(unnamed)} of {checked} model foreign keys are unnamed, so a database "
        "built by create_all() does not match one built by the migrations, and the "
        "next batch_alter_table() on those tables fails with 'Constraint must have a "
        f"name'. The convention belongs in database/base.py: {unnamed[:5]}"
    )


@pytest.mark.parametrize("table,expected", [
    ("spare_part_movement_documents",
     "fk_spare_part_movement_documents_source_document_id"),
    ("spare_part_movement_items",
     "fk_spare_part_movement_items_source_item_id"),
])
def test_a_fresh_database_names_its_keys_the_way_the_migration_does(table, expected):
    """The same constraint must not get two different names depending on the path."""
    from app.database import model_registry  # noqa: F401
    from app.database.base import Base

    names = {c.name for c in Base.metadata.tables[table].foreign_key_constraints}
    assert expected in names, (
        f"{table} would be created with {sorted(n for n in names if n)}, while "
        f"stage12 writes {expected!r} -- a fresh database and a migrated one would "
        "disagree about the same constraint"
    )