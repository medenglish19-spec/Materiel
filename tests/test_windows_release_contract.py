import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_windows_release_version_matches_packaged_branding():
    release_version = (ROOT / "windows" / "version.txt").read_text(
        encoding="utf-8"
    ).strip()
    branding = json.loads(
        (ROOT / "splash-screen" / "config.json").read_text(encoding="utf-8")
    )

    assert branding["version"] == release_version


def test_windows_installer_mutex_matches_packaged_launcher():
    installer = (ROOT / "windows" / "materiel.iss").read_text(encoding="utf-8-sig")

    assert "AppMutex=Local\\Materiel" in installer
