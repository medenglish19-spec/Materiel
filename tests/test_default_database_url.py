from pathlib import Path

from sqlalchemy.engine import make_url

from app.core import config
from app.core.config import default_database_url, resolve_database_url


def test_default_database_url_is_anchored_to_project_root():
    project_root = Path.cwd() / "launch-from-another-directory"
    expected_path = (project_root / "fleet_assets.db").resolve().as_posix()

    assert default_database_url(project_root) == f"sqlite:///{expected_path}"


def test_packaged_database_uses_persistent_directory_next_to_the_installer_setting(tmp_path, monkeypatch):
    install_dir = tmp_path / "installed-program"
    install_dir.mkdir()
    executable = install_dir / "Materiel.exe"
    executable.touch()
    user_data_dir = tmp_path / "MaterielData"
    (install_dir / "materiel-data-dir.txt").write_text(str(user_data_dir), encoding="utf-8")
    monkeypatch.setattr(config.sys, "executable", str(executable))
    monkeypatch.setattr(config.sys, "frozen", True, raising=False)

    database_url = default_database_url()

    assert make_url(database_url).database == (user_data_dir / "fleet_assets.db").resolve().as_posix()


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


def test_frozen_settings_use_secure_defaults_and_a_persistent_signing_key(tmp_path, monkeypatch):
    monkeypatch.setattr(config.sys, "frozen", True, raising=False)
    monkeypatch.setattr(config, "packaged_data_directory", lambda: tmp_path / "data")
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("DEV_DISABLE_AUTH", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)

    key = config.packaged_secret_key()

    assert config.default_environment() == "production"
    assert config.dev_auth_disabled() is False
    assert len(key) >= 32
    assert key != config.DEFAULT_SECRET_KEY
    assert config.packaged_secret_key() == key
    assert (tmp_path / "data" / "secret.key").read_text(encoding="utf-8") == key


def test_frozen_auth_cannot_be_disabled_by_environment_override(monkeypatch):
    monkeypatch.setattr(config.sys, "frozen", True, raising=False)
    monkeypatch.delenv("DEV_DISABLE_AUTH", raising=False)

    assert config.dev_auth_disabled() is False

    monkeypatch.setenv("DEV_DISABLE_AUTH", "true")

    assert config.dev_auth_disabled() is False
