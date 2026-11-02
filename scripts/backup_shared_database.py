"""Create a consistent SQLite snapshot using SQLite's online backup API."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3


def backup_database(database: Path, backup_dir: Path) -> Path:
    """Back up a live SQLite database and verify the snapshot is readable."""
    source = database.expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"database does not exist: {source}")

    destination_dir = backup_dir.expanduser().resolve()
    destination_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = destination_dir / f"{source.stem}.{timestamp}{source.suffix or '.db'}"
    partial = destination.with_name(destination.name + ".partial")
    if destination.exists() or partial.exists():
        raise FileExistsError(f"backup already exists: {destination}")

    source_connection: sqlite3.Connection | None = None
    backup_connection: sqlite3.Connection | None = None
    try:
        source_connection = sqlite3.connect(str(source), timeout=30)
        backup_connection = sqlite3.connect(str(partial), timeout=30)
        source_connection.backup(backup_connection, pages=256, sleep=0.05)
        backup_connection.commit()
        integrity = backup_connection.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise sqlite3.DatabaseError(
                f"backup integrity_check failed: {integrity[0] if integrity else 'no result'}"
            )
        backup_connection.close()
        backup_connection = None
        source_connection.close()
        source_connection = None
        partial.replace(destination)
        return destination
    except (OSError, sqlite3.Error):
        if backup_connection is not None:
            backup_connection.close()
        if source_connection is not None:
            source_connection.close()
        partial.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create a consistent SQLite backup")
    parser.add_argument("database", type=Path, help="SQLite database to back up")
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=None,
        help="destination folder (defaults to MATERIEL_DB_BACKUP_DIR or a sibling folder)",
    )
    args = parser.parse_args(argv)
    default_dir = Path(
        os.environ.get("MATERIEL_DB_BACKUP_DIR", args.database.parent / "database_backups")
    )
    try:
        destination = backup_database(args.database, args.backup_dir or default_dir)
    except (OSError, sqlite3.Error) as exc:
        parser.exit(1, f"backup failed: {exc}\n")
    print(f"backup created: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
