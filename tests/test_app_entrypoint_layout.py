"""Regression guard for the Python package/entrypoint layout."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_root_app_module_does_not_shadow_app_package():
    """The root app.py must never return and shadow the app/ package."""
    assert not (ROOT / "app.py").exists()
    assert (ROOT / "app").is_dir()
    assert (ROOT / "api" / "index.py").is_file()
