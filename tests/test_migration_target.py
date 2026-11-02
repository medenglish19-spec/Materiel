"""A migration must go to the database the caller named.

``migrations/env.py`` used to overwrite whatever URL the caller put in
``Config.set_main_option("sqlalchemy.url", ...)`` with ``settings.DATABASE_URL``
and migrate that instead. Nothing said so. A test that asked for a scratch file
wrote to the real database instead -- which is exactly what happened while
fixing the movement migration, and it left a stray ``_alembic_tmp_`` table
behind in the live database.

The order is now: the caller's URL, else the database the app is configured for.
That keeps the app path and the ``alembic`` CLI path on the app's database while
letting a caller aim somewhere else.

Every test here redirects ``settings.DATABASE_URL`` at a temporary file first, so
none of them can reach the real database even if the resolution is wrong.
"""

import ast
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402

from app.core.config import settings  # noqa: E402


def _config(url: str | None = None) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    if url is not None:
        config.set_main_option("sqlalchemy.url", url)
    return config


def _tables(path: Path) -> list[str]:
    if not path.exists():
        return []
    con = sqlite3.connect(path)
    try:
        return [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")]
    finally:
        con.close()


def test_alembic_ini_names_no_database(tmp_path, monkeypatch):
    """A URL in alembic.ini would outrank the caller without anyone seeing it."""
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{tmp_path}/x.db")

    assert _config().get_main_option("sqlalchemy.url") in (None, ""), (
        "alembic.ini pins sqlalchemy.url; env.py then has to choose between the "
        "caller and this file, and the caller's choice is the one that matters"
    )


def test_the_caller_can_point_a_migration_at_another_database(tmp_path, monkeypatch):
    """The decoy is what the app is configured for; it must be left alone."""
    scratch = tmp_path / "scratch.db"
    decoy = tmp_path / "decoy.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{decoy.as_posix()}")

    command.stamp(_config(f"sqlite:///{scratch.as_posix()}"), "head")

    assert "alembic_version" in _tables(scratch), (
        "the URL the caller passed was ignored -- the migration went elsewhere"
    )
    assert _tables(decoy) == [], (
        f"the database the app is configured for was written to: {_tables(decoy)}"
    )


def test_without_a_caller_url_it_migrates_the_configured_database(tmp_path, monkeypatch):
    """Both entry points the app relies on pass no URL; keep that working."""
    target = tmp_path / "configured.db"
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{target.as_posix()}")

    command.stamp(_config(), "head")

    assert "alembic_version" in _tables(target), (
        "with no URL on the Config the migration must fall back to "
        "settings.DATABASE_URL -- this is the path the app and CLI take"
    )


def test_a_percent_in_the_url_does_not_break_the_config(tmp_path, monkeypatch):
    """ConfigParser reads % as interpolation, so this has to survive a round trip."""
    target = tmp_path / "percent.db"
    url = f"sqlite:///{target.as_posix()}"
    monkeypatch.setattr(settings, "DATABASE_URL", url)

    config = _config(url.replace("%", "%%"))

    assert config.get_main_option("sqlalchemy.url") == url


def test_only_one_place_resolves_the_database_url():
    """The offline and online paths have to agree; a second lookup is how they drift."""
    tree = ast.parse((ROOT / "migrations" / "env.py").read_text(encoding="utf-8"))

    resolver = next(
        (n for n in tree.body
         if isinstance(n, ast.FunctionDef) and n.name == "_database_url"),
        None,
    )
    assert resolver is not None, "_database_url() is gone; the resolution moved"
    assert ast.get_docstring(resolver), (
        "_database_url needs a docstring saying which URL wins -- the precedence "
        "is the whole point of it"
    )

    inside = range(resolver.lineno, (resolver.end_lineno or resolver.lineno) + 1)
    strays = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr == "DATABASE_URL"
        and isinstance(node.value, ast.Name)
        and node.value.id == "settings"
        and node.lineno not in inside
    ]
    assert not strays, (
        f"env.py reads settings.DATABASE_URL outside _database_url at lines {strays}; "
        "resolve it in one place so the offline and online paths cannot disagree"
    )