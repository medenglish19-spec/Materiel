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
    launcher = (ROOT / "run_web.py").read_text(encoding="utf-8")

    assert "AppMutex=Local\\Materiel,Global\\Materiel" in installer
    assert "Global\\Materiel" in installer
    assert 'console=False' in (ROOT / "windows" / "Materiel.spec").read_text(encoding="utf-8")
    assert "_global_mutex_name" in launcher


def test_windows_installer_has_one_stable_setup_filename():
    installer = (ROOT / "windows" / "materiel.iss").read_text(encoding="utf-8-sig")
    build = (ROOT / "windows" / "build_windows.ps1").read_text(encoding="utf-8")

    assert "OutputBaseFilename=Materiel-Setup" in installer
    assert 'Join-Path $ReleaseRoot "Materiel-Setup.exe"' in build
