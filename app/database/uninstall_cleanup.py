"""Remove user authentication data when the Windows build is uninstalled.

The installer deliberately keeps the operational SQLite database and uploads
under the durable data directory (``%ProgramData%\\Materiel\\data`` by default)
so an update or a reinstall never destroys the organisation's history.

Uninstalling is different: the user identity must not survive.  This module
deletes the rows in the ``users`` table and the independent signing key used by
session cookies, while leaving every operational table (equipment, maintenance,
fuel, spare parts, readings, settings, ...) untouched.

The cleanup is invoked by Inno Setup through ``Materiel.exe
--uninstall-cleanup``.  It runs in its own short-lived process, so no web
server or SQLAlchemy connection is open while the transaction runs.

Safety rules implemented here:

* the database file is never deleted, re-created or re-initialised;
* the work is done in one ``BEGIN IMMEDIATE`` transaction;
* foreign-key columns that point at ``users`` are set to ``NULL`` instead of
  deleting the operational rows that own them;
* ``PRAGMA foreign_key_check`` must pass inside the transaction and
  ``PRAGMA integrity_check`` must pass before and after the commit;
* an update is detected through the marker written by the new setup and the
  cleanup is skipped, so upgrading never removes accounts;
* a missing, locked or corrupt database is reported without touching any other
  data.
"""

from __future__ import annotations

import ctypes
import json
import logging
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UPDATE_MARKER_ENV = "MATERIEL_UPDATE_MARKER"
ALLOW_CLEANUP_ENV = "MATERIEL_ALLOW_UNINSTALL_CLEANUP"
UPDATE_MARKER_MAX_AGE_SECONDS = 6 * 60 * 60
LOCK_RETRY_SECONDS = 30
LOCK_RETRY_INTERVAL = 0.5

# Files in the data directory that exist only for authentication.  Older builds
# wrote first-run credentials next to the database; current builds use only the
# signing key.  Both are removed so no credential material survives uninstall.
AUTH_ONLY_FILES = ("secret.key", "first-run-credentials.txt")

# The project logger (``app.core.logging``) imports ``app.core.config``, which
# creates ``secret.key`` while it is imported.  This module runs precisely when
# that key must stay deleted, so it deliberately uses the standard logger.
_LOGGER = logging.getLogger(__name__)


class UninstallCleanupError(RuntimeError):
    """Raised when authentication data cannot be removed safely."""


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def _program_data_root() -> Path:
    program_data = os.getenv("PROGRAMDATA")
    if program_data:
        return Path(program_data)
    local_data = os.getenv("LOCALAPPDATA")
    if local_data:
        return Path(local_data)
    return Path.home()


def _packaged_data_directory() -> Path:
    """Resolve the durable data directory without importing application settings.

    ``app.core.config`` creates ``secret.key`` while it is being imported.  The
    cleanup must not depend on that side effect (and must still work when the
    existing key is damaged), so the same lookup rules are applied locally.
    """
    executable = Path(sys.executable).resolve()
    override = os.getenv("MATERIEL_DATA_DIR")
    if override and override.strip():
        directory = Path(os.path.expandvars(override.strip())).expanduser()
        return directory if directory.is_absolute() else executable.parent / directory

    location_file = executable.parent / "materiel-data-dir.txt"
    try:
        configured = location_file.read_text(encoding="utf-8").strip()
    except OSError:
        configured = ""
    if configured:
        directory = Path(os.path.expandvars(configured)).expanduser()
        return directory if directory.is_absolute() else executable.parent / directory

    program_data = os.getenv("PROGRAMDATA")
    if program_data:
        return Path(program_data) / "Materiel" / "data"
    if os.name == "nt":
        local_data = os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(local_data) / "Materiel" / "data"
    return Path.home() / ".local" / "share" / "materiel" / "data"


def update_marker_path() -> Path:
    """Return the marker written by Setup while an update is running."""
    override = os.getenv(UPDATE_MARKER_ENV)
    if override and override.strip():
        return Path(os.path.expandvars(override.strip())).expanduser()
    return _program_data_root() / "Materiel" / "update-in-progress"


def _read_marker() -> tuple[int | None, float] | None:
    path = update_marker_path()
    try:
        raw = path.read_text(encoding="utf-8", errors="replace").strip()
        modified = path.stat().st_mtime
    except OSError:
        return None
    pid: int | None = None
    first = raw.split("|", 1)[0].strip()
    if first.isdigit():
        pid = int(first)
    return pid, modified


def _process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True

    process_query_limited_information = 0x1000
    still_active = 259
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def update_is_in_progress() -> bool:
    """Return True while the new Setup is upgrading an existing installation.

    Setup writes the marker before installation starts and removes it when the
    installation finishes.  The process id in the marker protects against a
    stale marker left behind by a setup process that was killed: an old marker
    whose process is gone is ignored (and removed) so a later real uninstall
    still removes the accounts.
    """
    marker = _read_marker()
    if marker is None:
        return False
    pid, modified = marker
    age = time.time() - modified
    if age <= UPDATE_MARKER_MAX_AGE_SECONDS and pid is not None and _process_is_alive(pid):
        return True
    if age <= UPDATE_MARKER_MAX_AGE_SECONDS and pid is None:
        # Older marker format: a fresh marker is enough to protect an update.
        return True
    try:
        update_marker_path().unlink()
    except OSError:
        pass
    return False


def _parent_process_name() -> str:
    """Return the executable name of the process that started this one."""
    if os.name != "nt":
        return ""
    try:
        import ctypes.wintypes as wintypes

        th32cs_snapprocess = 0x00000002
        invalid_handle_value = ctypes.c_void_p(-1).value

        class PROCESSENTRY32W(ctypes.Structure):
            _fields_ = [
                ("dwSize", wintypes.DWORD),
                ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD),
                ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD),
                ("pcPriClassBase", ctypes.c_long),
                ("dwFlags", wintypes.DWORD),
                ("szExeFile", wintypes.WCHAR * 260),
            ]

        kernel32 = ctypes.windll.kernel32
        snapshot = kernel32.CreateToolhelp32Snapshot(th32cs_snapprocess, 0)
        if snapshot == invalid_handle_value:
            return ""
        try:
            entries: dict[int, tuple[int, str]] = {}
            entry = PROCESSENTRY32W()
            entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
            more = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
            while more:
                entries[int(entry.th32ProcessID)] = (
                    int(entry.th32ParentProcessID),
                    str(entry.szExeFile),
                )
                more = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
            current = entries.get(os.getpid())
            if current is None:
                return ""
            parent = entries.get(current[0])
            return parent[1] if parent else ""
        finally:
            kernel32.CloseHandle(snapshot)
    except Exception:
        return ""


def _called_by_uninstaller() -> bool:
    if _truthy(os.getenv(ALLOW_CLEANUP_ENV)):
        return True
    parent = _parent_process_name().strip().lower()
    return parent.startswith("unins") and (parent.endswith(".exe") or parent.endswith(".tmp"))


def _connect(database_path: Path) -> sqlite3.Connection:
    deadline = time.monotonic() + LOCK_RETRY_SECONDS
    while True:
        try:
            connection = sqlite3.connect(
                database_path,
                timeout=5,
                isolation_level=None,
            )
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")
            # Overwrite deleted authentication rows instead of leaving the
            # password hashes in free pages of the database file.
            connection.execute("PRAGMA secure_delete=ON")
            return connection
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or time.monotonic() >= deadline:
                raise
            time.sleep(LOCK_RETRY_INTERVAL)


def _table_columns(connection: sqlite3.Connection, table: str) -> dict[str, dict[str, Any]]:
    return {
        str(row[1]): {
            "notnull": bool(row[3]),
            "primary_key": bool(row[5]),
        }
        for row in connection.execute(f'PRAGMA table_info("{table}")')
    }


def _user_reference_columns(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    tables = [
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]
    references: list[dict[str, Any]] = []
    for table in tables:
        if table == "users":
            continue
        columns = _table_columns(connection, table)
        for row in connection.execute(f'PRAGMA foreign_key_list("{table}")'):
            # row: id, seq, table, from, to, on_update, on_delete, match
            if str(row[2]) != "users":
                continue
            column = str(row[3])
            info = columns.get(column, {})
            references.append(
                {
                    "table": table,
                    "column": column,
                    "notnull": bool(info.get("notnull")),
                    "on_delete": str(row[6]),
                }
            )
    return references


def _database_integrity(connection: sqlite3.Connection) -> str:
    rows = [str(row[0]) for row in connection.execute("PRAGMA integrity_check")]
    return "ok" if rows == ["ok"] else "; ".join(rows)


def _foreign_key_violations(connection: sqlite3.Connection) -> list[tuple[Any, ...]]:
    return [tuple(row) for row in connection.execute("PRAGMA foreign_key_check")]


def _checkpoint(connection: sqlite3.Connection) -> None:
    try:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.DatabaseError:
        # Rollback-journal databases have no WAL to checkpoint.
        pass


def remove_user_accounts(
    database_path: str | Path,
    *,
    data_directory: str | Path | None = None,
) -> dict[str, Any]:
    """Delete all user accounts from *database_path* without touching business data.

    ``data_directory`` is where the packaged ``secret.key`` lives.  When it is
    supplied the key is removed after the database transaction succeeds, which
    invalidates every existing session cookie.
    """
    path = Path(database_path)
    result: dict[str, Any] = {
        "database": str(path),
        "status": "ok",
        "users_deleted": 0,
        "references_cleared": {},
        "integrity_check": None,
        "foreign_key_violations": 0,
        "secret_key_removed": False,
    }

    if not path.exists():
        result["status"] = "database_missing"
    else:
        connection: sqlite3.Connection | None = None
        try:
            connection = _connect(path)
            integrity_before = _database_integrity(connection)
            if integrity_before != "ok":
                raise UninstallCleanupError(
                    f"SQLite integrity_check failed before cleanup: {integrity_before}"
                )

            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if "users" not in tables:
                result["status"] = "users_table_missing"
            else:
                references = _user_reference_columns(connection)
                blocking = [
                    reference
                    for reference in references
                    if reference["notnull"]
                ]
                if blocking:
                    details = ", ".join(
                        f'{item["table"]}.{item["column"]}' for item in blocking
                    )
                    raise UninstallCleanupError(
                        "Cannot remove user accounts without deleting operational "
                        f"rows because these user references are NOT NULL: {details}"
                    )

                connection.execute("BEGIN IMMEDIATE")
                try:
                    for reference in references:
                        table = reference["table"]
                        column = reference["column"]
                        cursor = connection.execute(
                            f'UPDATE "{table}" SET "{column}" = NULL '
                            f'WHERE "{column}" IS NOT NULL'
                        )
                        if cursor.rowcount:
                            result["references_cleared"][f"{table}.{column}"] = cursor.rowcount

                    cursor = connection.execute("DELETE FROM users")
                    result["users_deleted"] = max(cursor.rowcount, 0)

                    remaining = connection.execute(
                        "SELECT COUNT(*) FROM users"
                    ).fetchone()[0]
                    if remaining:
                        raise UninstallCleanupError(
                            f"{remaining} user row(s) remained after DELETE"
                        )

                    violations = _foreign_key_violations(connection)
                    if violations:
                        raise UninstallCleanupError(
                            f"foreign_key_check reported {len(violations)} violation(s): "
                            f"{violations[:5]}"
                        )
                    connection.execute("COMMIT")
                except BaseException:
                    try:
                        connection.execute("ROLLBACK")
                    except sqlite3.DatabaseError:
                        pass
                    raise

                result["integrity_check"] = _database_integrity(connection)
                if result["integrity_check"] != "ok":
                    raise UninstallCleanupError(
                        "SQLite integrity_check failed after cleanup: "
                        f'{result["integrity_check"]}'
                    )
                result["foreign_key_violations"] = len(_foreign_key_violations(connection))
                _checkpoint(connection)
        finally:
            if connection is not None:
                connection.close()

    if data_directory is not None:
        _remove_auth_files(Path(data_directory), result)

    return result


def _remove_auth_files(data_directory: Path, result: dict[str, Any]) -> None:
    removed: list[str] = []
    for name in AUTH_ONLY_FILES:
        path = data_directory / name
        try:
            if path.is_file():
                path.unlink()
                removed.append(name)
        except OSError as exc:
            result["status"] = "auth_file_not_removed"
            result.setdefault("auth_file_errors", {})[name] = str(exc)
    result["auth_files_removed"] = removed
    result["secret_key_removed"] = "secret.key" in removed


def _write_cleanup_log(data_directory: Path, payload: dict[str, Any]) -> None:
    line = json.dumps(
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **payload,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    candidates = [
        data_directory / "uninstall-auth-cleanup.log",
        _program_data_root() / "Materiel" / "uninstall-auth-cleanup.log",
    ]
    for path in candidates:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
            return
        except OSError:
            continue
    # Windowed executables have no usable stderr; log as a last resort so the
    # failure is never completely silent.
    _LOGGER.error("Uninstall authentication cleanup: %s", line)


def run_uninstall_cleanup() -> int:
    """Entry point used by ``Materiel.exe --uninstall-cleanup``.

    Returns 0 on success (including an update being detected) and 1 when the
    cleanup could not be completed.  The uninstaller continues either way, but
    a clear log entry is written so the failure is never silent.
    """
    data_directory = _packaged_data_directory()
    payload: dict[str, Any] = {
        "database": str(data_directory / "fleet_assets.db"),
        "status": "ok",
        "users_deleted": 0,
        "references_cleared": {},
        "integrity_check": None,
        "foreign_key_violations": 0,
        "secret_key_removed": False,
    }

    if not getattr(sys, "frozen", False) and not _truthy(os.getenv(ALLOW_CLEANUP_ENV)):
        payload["status"] = "refused_non_packaged_run"
        _write_cleanup_log(data_directory, payload)
        return 2

    if update_is_in_progress():
        payload["status"] = "update_in_progress"
        _write_cleanup_log(data_directory, payload)
        return 0

    if not _called_by_uninstaller():
        payload["status"] = "refused_not_called_by_uninstaller"
        _write_cleanup_log(data_directory, payload)
        return 2

    try:
        payload.update(
            remove_user_accounts(
                data_directory / "fleet_assets.db",
                data_directory=data_directory,
            )
        )
        status = str(payload.get("status", "ok"))
        _write_cleanup_log(data_directory, payload)
        if status in {"ok", "database_missing", "users_table_missing"}:
            return 0
        return 1
    except Exception as exc:
        payload["status"] = "failed"
        payload["error"] = f"{type(exc).__name__}: {exc}"
        _write_cleanup_log(data_directory, payload)
        return 1
