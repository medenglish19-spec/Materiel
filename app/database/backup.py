"""Verified SQLite backups used before application schema upgrades."""

from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from contextlib import closing

from sqlalchemy.engine import make_url

from app.core.logging import get_logger


logger = get_logger(__name__)


def sqlite_database_path(database_url: str) -> Path | None:
    url = make_url(database_url)
    if not url.drivername.startswith("sqlite") or not url.database:
        return None
    if url.database == ":memory:" or url.database.startswith("file:"):
        return None
    return Path(url.database).resolve()


def backup_sqlite_database(database_url: str) -> Path | None:
    """Create and integrity-check a dated SQLite backup; fail closed on errors."""
    database_path = sqlite_database_path(database_url)
    if database_path is None or not database_path.is_file() or database_path.stat().st_size == 0:
        return None

    backup_dir = database_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    backup_path = backup_dir / f"{database_path.stem}.before-upgrade-{stamp}.db"

    try:
        with closing(sqlite3.connect(database_path, timeout=30)) as source:
            with closing(sqlite3.connect(backup_path, timeout=30)) as backup:
                source.backup(backup)
                result = backup.execute("PRAGMA integrity_check").fetchone()
                if not result or result[0] != "ok":
                    raise sqlite3.DatabaseError(f"Backup integrity check failed: {result!r}")
                backup.commit()
    except Exception:
        backup_path.unlink(missing_ok=True)
        logger.exception("Could not create a verified database backup: %s", database_path)
        raise

    logger.info("Verified pre-upgrade database backup created: %s", backup_path)
    return backup_path


def restore_sqlite_database(backup_path: Path, database_url: str) -> None:
    """Restore a previously verified backup after a failed schema upgrade."""
    database_path = sqlite_database_path(database_url)
    if database_path is None:
        raise ValueError("Automatic restore is available only for file-based SQLite databases")
    if not backup_path.is_file():
        raise FileNotFoundError(backup_path)

    database_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(backup_path, timeout=30)) as backup:
        with closing(sqlite3.connect(database_path, timeout=30)) as target:
            backup.backup(target)
            result = target.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise sqlite3.DatabaseError(f"Restored database integrity check failed: {result!r}")
            target.commit()
    logger.warning("Restored database after failed upgrade: %s", database_path)
