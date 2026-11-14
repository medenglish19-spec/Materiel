"""Resolve the durable data directory without importing application settings.

``app.core.config`` creates ``secret.key`` as an import side effect, so the
uninstaller cannot import it while it is trying to preserve (or explicitly
remove) authentication files.  This module keeps the lookup rules in one place
and has no side effects of its own.

Resolution order for an installed copy:

1. ``MATERIEL_DATA_DIR`` (explicit operator override);
2. ``materiel-data-dir.txt`` next to the executable;
3. the ``HKCU\\Software\\Materiel\\DataDir`` value written by Setup;
4. an existing ``<drive>:\\MaterielData`` folder that already holds a database
   or signing key (this is what lets an update find a custom location even when
   the sidecar file was lost);
5. an existing ``%ProgramData%\\Materiel\\data`` or ``%LOCALAPPDATA%\\Materiel\\data``;
6. the default ``%ProgramData%\\Materiel\\data``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

DATABASE_FILENAME = "fleet_assets.db"
SECRET_KEY_FILENAME = "secret.key"
REGISTRY_SUBKEY = r"Software\Materiel"
REGISTRY_VALUE = "DataDir"


def _expand(value: str, executable: Path) -> Path:
    directory = Path(os.path.expandvars(value.strip())).expanduser()
    return directory if directory.is_absolute() else executable.parent / directory


def registry_data_directory() -> Path | None:
    if os.name != "nt":
        return None
    try:
        import winreg
    except ImportError:  # pragma: no cover - non-Windows
        return None
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(root, REGISTRY_SUBKEY) as key:
                value, _ = winreg.QueryValueEx(key, REGISTRY_VALUE)
        except OSError:
            continue
        if isinstance(value, str) and value.strip():
            return Path(os.path.expandvars(value.strip())).expanduser()
    return None


def _looks_like_data_directory(path: Path) -> bool:
    return (path / DATABASE_FILENAME).is_file() or (path / SECRET_KEY_FILENAME).is_file()


def _drive_roots() -> list[Path]:
    """Enumerate local drive roots without touching disconnected network shares."""
    lister = getattr(os, "listdrives", None)
    if callable(lister):
        try:
            return [Path(drive) for drive in lister()]
        except OSError:  # pragma: no cover - defensive
            pass
    return [Path(f"{letter}:\\") for letter in "CDEFGH"]


def discovered_data_directory() -> Path | None:
    """Return an existing custom ``MaterielData`` folder, if one is found."""
    candidates: list[Path] = []
    registry = registry_data_directory()
    if registry is not None:
        candidates.append(registry)
    for root in _drive_roots():
        candidates.append(root / "MaterielData")
    for candidate in (Path(os.getenv("PROGRAMDATA", "")) if os.getenv("PROGRAMDATA") else None,
                      Path(os.getenv("LOCALAPPDATA", "")) if os.getenv("LOCALAPPDATA") else None):
        if candidate is not None:
            candidates.append(candidate / "Materiel" / "data")
    for candidate in candidates:
        try:
            if _looks_like_data_directory(candidate):
                return candidate
        except OSError:  # pragma: no cover - inaccessible drive
            continue
    return None


def packaged_data_directory(executable: Path | None = None) -> Path:
    executable = (executable or Path(sys.executable)).resolve()

    override = os.getenv("MATERIEL_DATA_DIR")
    if override and override.strip():
        return _expand(override, executable)

    location_file = executable.parent / "materiel-data-dir.txt"
    try:
        configured = location_file.read_text(encoding="utf-8").strip()
    except OSError:
        configured = ""
    if configured:
        return _expand(configured, executable)

    registry = registry_data_directory()
    if registry is not None:
        return registry

    discovered = discovered_data_directory()
    if discovered is not None:
        return discovered

    program_data = os.getenv("PROGRAMDATA")
    if program_data:
        return Path(program_data) / "Materiel" / "data"
    if os.name == "nt":
        local_data = os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(local_data) / "Materiel" / "data"
    return Path.home() / ".local" / "share" / "materiel" / "data"
