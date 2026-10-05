"""A failed log rotation must not cost you the log record.

This is not hypothetical. Running ``alembic upgrade`` on the live database
produced this on stderr:

    --- Logging error ---
    Traceback (most recent call last):
    PermissionError: [WinError 32] ... 'logs\\app.log' -> 'logs\\app.log.1'

because another server was holding ``app.log`` open, and on Windows a rename
over an open file fails. ``RotatingFileHandler.doRollover()`` lets that OSError
escape ``emit()``, so the record being written at that moment is dropped and the
traceback is printed instead of the message it was meant to announce.

The tests pin the two halves: rotation still works when it can, and when it
cannot the record still lands in the file.
"""

import logging
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.logging import (  # noqa: E402
    _TolerantRotatingFileHandler,
    _build_output_handlers,
)


def test_the_running_app_actually_uses_the_tolerant_handler(tmp_path, monkeypatch):
    """Otherwise the class is correct code that nothing runs."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "LOG_DIR", str(tmp_path))
    monkeypatch.setattr(settings, "LOG_LEVEL", "INFO")

    from logging.handlers import BaseRotatingHandler

    handlers = _build_output_handlers()
    try:
        # RotatingFileHandler descends from BaseRotatingHandler, not FileHandler,
        # so that is the base class to look for
        files = [h for h in handlers if isinstance(h, BaseRotatingHandler)]
        assert files, f"no rotating file handler is configured: {handlers}"
        assert isinstance(files[0], _TolerantRotatingFileHandler), (
            f"the app logs through {type(files[0]).__name__}, which drops records "
            f"when rotation fails"
        )
    finally:
        for h in handlers:
            h.close()


def _handler(path: Path, max_bytes: int = 60, backups: int = 2):
    handler = _TolerantRotatingFileHandler(
        path, maxBytes=max_bytes, backupCount=backups, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    return handler


def test_a_record_written_when_rotation_fails_is_not_lost(tmp_path, monkeypatch):
    """The failure mode that actually happened: rollover denied, record kept."""
    log = tmp_path / "app.log"
    handler = _handler(log)
    handler.setLevel(logging.INFO)
    # force the size past the limit so emit() tries to roll over
    handler.stream.write("x" * 40)
    handler.stream.flush()

    def deny(*args, **kwargs):
        raise PermissionError(32, "file is used by another process")

    monkeypatch.setattr(os, "rename", deny)

    try:
        handler.emit(logging.LogRecord(
            "app", logging.INFO, __file__, 1, "المرور يسجل", None, None))
    finally:
        handler.close()

    assert "المرور يسجل" in log.read_text(encoding="utf-8"), (
        "the record was dropped because rotation failed -- this is the bug"
    )


def test_a_denied_rotation_does_not_print_a_logging_error(tmp_path, monkeypatch,
                                                          capsys):
    """The traceback replaces the message; it must not replace it on stderr."""
    log = tmp_path / "app.log"
    handler = _handler(log)
    handler.setLevel(logging.INFO)
    handler.stream.write("x" * 40)
    handler.stream.flush()

    monkeypatch.setattr(os, "rename", lambda *a, **k: (_ for _ in ()).throw(
        PermissionError(32, "locked")))

    try:
        handler.emit(logging.LogRecord(
            "app", logging.INFO, __file__, 1, "after the failure", None, None))
    finally:
        handler.close()

    assert "--- Logging error ---" not in capsys.readouterr().err


def test_rotation_still_happens_when_the_file_is_free(tmp_path):
    """Tolerating failure must not turn into never rotating."""
    log = tmp_path / "app.log"
    handler = _handler(log, max_bytes=60, backups=2)
    handler.setLevel(logging.INFO)

    try:
        for i in range(6):
            handler.emit(logging.LogRecord(
                "app", logging.INFO, __file__, 1, f"سطر {i} " + "ي" * 20,
                None, None))
    finally:
        handler.close()

    assert (tmp_path / "app.log.1").exists(), "rotation never happened"
    # backups are capped, so only what is still on disk can be asserted
    kept = "".join(
        p.read_text(encoding="utf-8")
        for p in sorted(tmp_path.glob("app.log*"))
    )
    assert "سطر 5" in kept, "the newest record was lost"


def test_a_denied_rotation_leaves_the_file_readable(tmp_path, monkeypatch):
    """After swallowing the error the handler still owns a usable stream."""
    log = tmp_path / "app.log"
    handler = _handler(log)
    handler.stream.write("x" * 40)
    handler.stream.flush()

    monkeypatch.setattr(os, "rename", lambda *a, **k: (_ for _ in ()).throw(
        PermissionError(32, "locked")))

    try:
        handler.doRollover()  # must not raise
        assert handler.stream is not None
        handler.stream.write("still open\n")
        handler.stream.flush()
    finally:
        handler.close()

    assert "still open" in log.read_text(encoding="utf-8")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))