"""Persistent storage locations for user-uploaded files."""

from pathlib import Path
import shutil
import sys

from app.core.config import PROJECT_ROOT, packaged_data_directory
from app.core.logging import get_logger


logger = get_logger(__name__)


def uploads_directory(source_file: Path | str | None = None) -> Path:
    if getattr(sys, "frozen", False):
        return packaged_data_directory() / "uploads"
    if source_file is not None:
        return Path(source_file).resolve().parents[3] / "static" / "uploads"
    return PROJECT_ROOT / "static" / "uploads"


def migrate_packaged_uploads(project_root: Path | None = None) -> None:
    """Copy legacy bundled uploads once, preserving existing external files."""
    if not getattr(sys, "frozen", False):
        return
    source_root = (project_root or PROJECT_ROOT) / "static" / "uploads"
    target_root = uploads_directory()
    marker = target_root.parent / ".legacy-uploads-migrated"
    if marker.exists():
        return

    target_root.mkdir(parents=True, exist_ok=True)
    if source_root.is_dir():
        for source in source_root.rglob("*"):
            if not source.is_file():
                continue
            target = target_root / source.relative_to(source_root)
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    marker.write_text("ok\n", encoding="utf-8")
    logger.info("Legacy packaged uploads copied to persistent storage: %s", target_root)
