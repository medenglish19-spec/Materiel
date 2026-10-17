"""A failed migration must be visible.

Three separate things used to hide it, and all three are checked here:

1. ``migrations/env.py`` ran ``fileConfig(alembic.ini)``, which sets
   ``disabled=True`` on every logger that already exists and drops the app's
   ``QueueHandler`` off the root logger. Every message logged after that --
   including ``logger.exception`` for the failure -- went nowhere.
2. ``_run_alembic_upgrade`` listed the tables *before* logging, so when the
   database itself was the thing that failed, the error handler raised too and
   the real cause was replaced by one from the error handler.
3. ``shutdown_logging()`` only ran on the happy path, so the traceback was
   still queued when the process died and never reached stderr or app.log.

The app drains its log through a background listener in its own process, so
these tests drive real subprocesses and read the real ``app.log`` the app would
have written. Nothing here touches ``fleet_assets.db``.
"""

import json
import logging
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

CAUSE = "no_such_revision"


def _run(tmp_path: Path, body: str, db_name: str):
    """Run a snippet in its own process with the app's logging pointed at tmp."""
    logs = tmp_path / f"logs-{db_name}"
    logs.mkdir(exist_ok=True)
    env = os.environ.copy()
    env.update(
        {
            "PYTHONIOENCODING": "utf-8",
            "PYTHONPATH": str(ROOT),
            "SECRET_KEY": "ci-log-smoke-secret",
            "UVICORN_RELOAD": "false",
            "LOG_DIR": str(logs),
            "LOG_LEVEL": "INFO",
            "DATABASE_URL": f"sqlite:///{(tmp_path / db_name).as_posix()}",
        }
    )
    proc = subprocess.run(
        [sys.executable, "-c", body],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
    )
    app_log = logs / "app.log"
    text = app_log.read_text(encoding="utf-8") if app_log.exists() else ""
    return proc, text


def _corrupt_stamp(tmp_path: Path, db_name: str = "corrupt.db") -> Path:
    """A real database whose alembic_version names a revision that does not exist.

    This is a failure *inside* the migration, which is the case that used to be
    reported as a bare exit code with no output anywhere.
    """
    body = (
        "from app.core.logging import configure_logging, shutdown_logging\n"
        "from app.database.init_db import init_db\n"
        "configure_logging()\n"
        "init_db()\n"
        "shutdown_logging()\n"
    )
    proc, _ = _run(tmp_path, body, db_name)
    assert proc.returncode == 0, f"could not build the schema:\n{proc.stdout}\n{proc.stderr}"

    db = tmp_path / db_name
    with sqlite3.connect(db) as con:
        con.execute("UPDATE alembic_version SET version_num=?", (CAUSE,))
    return db


def test_the_app_logger_survives_running_a_migration(tmp_path):
    """A message logged after a migration must still reach app.log."""
    body = (
        "import logging\n"
        "from app.core.logging import configure_logging, shutdown_logging\n"
        "from app.database.init_db import init_db\n"
        "configure_logging()\n"
        "init_db()\n"
        "logging.getLogger('app.database.init_db').info('SENTINEL-AFTER-MIGRATION')\n"
        "shutdown_logging()\n"
    )
    proc, app_log = _run(tmp_path, body, "probe.db")

    assert "SENTINEL-AFTER-MIGRATION" in app_log, (
        "the app's logger was silenced by the migration; "
        f"app.log holds {app_log.strip()[-400:]!r}"
    )


def test_the_apps_log_handler_is_not_stripped_by_a_migration(tmp_path):
    """The root logger must keep the QueueHandler that feeds app.log."""
    body = (
        "import json, logging\n"
        "from app.core.logging import configure_logging\n"
        "from app.database.init_db import init_db\n"
        "configure_logging()\n"
        "init_db()\n"
        "root = logging.getLogger()\n"
        "print(json.dumps({\n"
        "    'disabled': logging.getLogger('app.database.init_db').disabled,\n"
        "    'root_handlers': [type(h).__name__ for h in root.handlers],\n"
        "}))\n"
    )
    proc, _ = _run(tmp_path, body, "probe.db")
    assert proc.returncode == 0, proc.stderr
    state = json.loads(proc.stdout.strip().splitlines()[-1])

    assert state["disabled"] is False, "the app's logger was disabled by the migration"
    assert "_SafeQueueHandler" in state["root_handlers"], (
        f"the app's queue handler was removed by the migration: {state['root_handlers']}"
    )


def test_run_web_names_the_cause_when_a_migration_fails(tmp_path):
    """The original symptom, end to end: run_web.py must not exit silently.

    Its alembic_version names a revision that does not exist, so command.upgrade
    fails *after* migrations/env.py has been imported. This used to exit 3 with
    the cause appearing in no output at all.
    """
    build = (
        "from app.core.logging import configure_logging, shutdown_logging\n"
        "from app.database.init_db import init_db\n"
        "configure_logging()\n"
        "init_db()\n"
        "shutdown_logging()\n"
    )
    env = {**os.environ, "PYTHONPATH": str(ROOT), "DATABASE_URL":
           f"sqlite:///{(tmp_path / 'stamp.db').as_posix()}"}
    built = subprocess.run([sys.executable, "-c", build], cwd=ROOT, env=env,
                           capture_output=True, text=True, encoding="utf-8", timeout=180)
    assert built.returncode == 0, f"could not build the schema:\n{built.stderr}"

    db = tmp_path / "stamp.db"
    with sqlite3.connect(db) as con:
        con.execute("UPDATE alembic_version SET version_num=?", (CAUSE,))

    logs = tmp_path / "logs-e2e"
    logs.mkdir()
    run = subprocess.run(
        [sys.executable, "run_web.py"],
        cwd=ROOT,
        env={**env, "SECRET_KEY": "ci-log-smoke-secret", "UVICORN_RELOAD": "false",
             "LOG_LEVEL": "INFO", "LOG_DIR": str(logs), "APP_HOST": "127.0.0.1",
             "APP_PORT": "59983"},
        capture_output=True, text=True, encoding="utf-8", timeout=180,
    )
    console = (run.stdout or "") + (run.stderr or "")
    app_log = logs / "app.log"
    logged = app_log.read_text(encoding="utf-8") if app_log.exists() else ""

    assert run.returncode != 0, "the corrupted stamp was supposed to fail startup"
    assert CAUSE in console, f"run_web.py exited without naming the cause:\n{console[-600:]}"
    assert CAUSE in logged, f"app.log does not name the cause; it holds {logged[-400:]!r}"


def test_a_failed_migration_reports_its_real_cause(tmp_path):
    """The traceback and its cause must be in the log, not only raised."""
    _corrupt_stamp(tmp_path)
    body = (
        "from app.core.logging import configure_logging, shutdown_logging\n"
        "from app.database.init_db import init_db\n"
        "configure_logging()\n"
        "try:\n"
        "    init_db()\n"
        "    print('INIT-DB-RETURNED')\n"
        "except BaseException as exc:\n"
        "    print('INIT-DB-RAISED: %s: %s' % (type(exc).__name__, exc))\n"
        "finally:\n"
        "    shutdown_logging()\n"
    )
    proc, app_log = _run(tmp_path, body, "corrupt.db")

    assert "INIT-DB-RETURNED" not in proc.stdout, "the corrupted stamp was supposed to fail"
    assert "INIT-DB-RAISED" in proc.stdout, f"init_db did not fail cleanly:\n{proc.stdout}\n{proc.stderr}"
    assert "Alembic upgrade failed" in app_log, (
        f"the migration failure was never logged; app.log holds {app_log.strip()[-400:]!r}"
    )
    assert CAUSE in app_log, (
        f"the real cause is missing from the log; app.log holds {app_log.strip()[-400:]!r}"
    )
    assert "Traceback" in app_log, "the log carries no traceback"


def test_the_cause_is_logged_even_when_the_diagnostics_fail(monkeypatch, caplog):
    """The error handler must not be able to swallow the error it reports.

    Listing the tables after a failed migration needs a working database. When
    the database is what failed, that call raises too -- so it has to happen
    after the failure is on the record, never before.
    """
    import app.database.init_db as init_db_module

    def upgrade(*_a, **_k):
        raise ValueError("MIGRATION-CAUSE")

    def inspect(*_a, **_k):
        raise TypeError("DIAGNOSTIC-CAUSE")

    monkeypatch.setattr(init_db_module.command, "upgrade", upgrade)
    monkeypatch.setattr(init_db_module, "inspect", inspect)

    with caplog.at_level(logging.ERROR, logger="app.database.init_db"):
        # the migration's own error is what must come out
        with pytest.raises(ValueError, match="MIGRATION-CAUSE"):
            init_db_module._run_alembic_upgrade(object())

    assert "Alembic upgrade failed" in caplog.text, (
        f"the failure was never logged; the handler raised instead. log: {caplog.text[-300:]!r}"
    )
    assert "MIGRATION-CAUSE" in caplog.text, (
        f"the log does not carry the real cause: {caplog.text[-300:]!r}"
    )


def test_the_lifespan_drains_the_log_queue_when_startup_fails(monkeypatch):
    """shutdown_logging() drains the queue, so a failing startup must reach it.

    Otherwise the traceback is still queued when the process dies, and the
    failure is lost with it.
    """
    import web.main as web_main
    from fastapi.testclient import TestClient

    drained = []
    monkeypatch.setattr(web_main, "configure_logging", lambda: None)
    monkeypatch.setattr(web_main, "shutdown_logging", lambda: drained.append("drained"))

    def broken():
        raise RuntimeError("startup failed")

    monkeypatch.setattr(web_main, "init_db", broken)

    app = web_main.create_app()
    with pytest.raises(RuntimeError, match="startup failed"):
        with TestClient(app):
            pass

    assert drained == ["drained"], (
        "the lifespan skipped shutdown_logging() when startup failed, so the "
        "queued traceback dies with the process"
    )

