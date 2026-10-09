"""Serverless logging must not attempt writes to Vercel's read-only filesystem."""

import logging

from app.core import logging as logging_module


def test_vercel_logging_uses_stderr_without_creating_log_directory(monkeypatch, tmp_path):
    log_dir = tmp_path / "logs"
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setattr(logging_module.settings, "LOG_DIR", str(log_dir))

    handlers = logging_module._build_output_handlers()
    try:
        assert len(handlers) == 1
        assert isinstance(handlers[0], logging.StreamHandler)
        assert not log_dir.exists()
    finally:
        for handler in handlers:
            handler.close()


def test_local_logging_keeps_rotating_file_handler(monkeypatch, tmp_path):
    log_dir = tmp_path / "logs"
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setattr(logging_module.settings, "LOG_DIR", str(log_dir))

    handlers = logging_module._build_output_handlers()
    try:
        assert len(handlers) == 2
        assert any(isinstance(h, logging.StreamHandler) for h in handlers)
        assert any(isinstance(h, logging_module._TolerantRotatingFileHandler) for h in handlers)
        assert (log_dir / "app.log").exists()
    finally:
        for handler in handlers:
            handler.close()
