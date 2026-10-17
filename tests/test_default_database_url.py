from pathlib import Path

from sqlalchemy.engine import make_url

from app.core.config import default_database_url, resolve_database_url


def test_default_database_url_is_anchored_to_project_root():
    project_root = Path.cwd() / "launch-from-another-directory"
    expected_path = (project_root / "fleet_assets.db").resolve().as_posix()

    assert default_database_url(project_root) == f"sqlite:///{expected_path}"


def test_relative_sqlite_override_is_also_anchored_to_project_root():
    project_root = Path.cwd() / "launch-from-another-directory"
    expected_path = (project_root / "fleet_assets.dev.db").resolve().as_posix()

    resolved = resolve_database_url("sqlite:///./fleet_assets.dev.db", project_root)

    assert make_url(resolved).database == expected_path


def test_absolute_sqlite_override_is_preserved():
    absolute_path = (Path.cwd() / "custom.db").resolve()
    url = f"sqlite:///{absolute_path.as_posix()}"

    assert resolve_database_url(url) == url


def test_startup_database_path_uses_the_decoded_resolved_sqlite_path(monkeypatch):
    from web import main

    project_root = Path.cwd() / "launch-from-another-directory"
    expected_path = (project_root / "fleet_assets.dev.db").resolve().as_posix()
    monkeypatch.setattr(
        main.settings,
        "DATABASE_URL",
        resolve_database_url("sqlite:///./fleet_assets.dev.db", project_root),
    )

    assert main._database_file() == expected_path
