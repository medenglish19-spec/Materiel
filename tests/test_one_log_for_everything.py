"""One log for the whole application, whichever entry point you use.

``migrations/env.py`` used to run ``fileConfig(alembic.ini)``, which replaced
the root handler and disabled every logger that already existed. Inside the
app that meant everything logged after the migration started went nowhere;
under the ``alembic`` CLI it meant alembic's own messages went to its own
stream instead of ``logs/app.log``, so a migration run had two homes.

Now the app configures logging once and Alembic joins it. These tests check
both entry points end up writing to the same file, in the same format.
"""

import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(tmp_path: Path, args, db_name="u.db"):
    logs = tmp_path / f"logs-{db_name}"
    logs.mkdir(exist_ok=True)
    env = os.environ.copy()
    env.update({
        "PYTHONIOENCODING": "utf-8",
        "PYTHONPATH": str(ROOT),
        "SECRET_KEY": "ci-unified-log-secret",
        "UVICORN_RELOAD": "false",
        "LOG_DIR": str(logs),
        "LOG_LEVEL": "INFO",
        "DATABASE_URL": f"sqlite:///{(tmp_path / db_name).as_posix()}",
    })
    proc = subprocess.run([sys.executable, *args], cwd=ROOT, env=env,
                          capture_output=True, text=True, encoding="utf-8", timeout=180)
    app_log = logs / "app.log"
    return proc, (app_log.read_text(encoding="utf-8") if app_log.exists() else "")


BUILD = (
    "from app.core.logging import configure_logging, shutdown_logging\n"
    "from app.database.init_db import init_db\n"
    "configure_logging()\n"
    "init_db()\n"
    "shutdown_logging()\n"
)


def _prepared(tmp_path, db_name="u.db"):
    """A schema built through init_db(), so alembic_version sits at head."""
    built, _ = _run(tmp_path, ["-c", BUILD], db_name)
    assert built.returncode == 0, built.stderr
    return tmp_path / db_name


def test_the_alembic_cli_writes_into_the_app_log(tmp_path):
    """A migration run from the command line must land in logs/app.log."""
    _prepared(tmp_path)

    up, app_log = _run(tmp_path, ["-m", "alembic", "upgrade", "head"])

    assert up.returncode == 0, up.stdout + up.stderr
    assert "alembic.runtime.migration" in app_log, (
        f"the CLI's migration output never reached logs/app.log; it holds {app_log[-300:]!r}"
    )
    assert "Will assume non-transactional DDL" in app_log, (
        "alembic ran but its own output is not in the app log"
    )


def test_the_app_and_the_cli_use_one_format(tmp_path):
    """Both entry points must produce the same log line shape."""
    _prepared(tmp_path)
    from_app = _run(tmp_path, ["-c", BUILD], "fmt-app.db")[1]
    from_cli = _run(tmp_path, ["-m", "alembic", "upgrade", "head"])[1]

    def shape(text, who):
        lines = [ln for ln in text.splitlines() if " INFO " in ln or " ERROR " in ln]
        assert lines, f"{who} produced no log lines at all"
        # the app's format is "<asctime> <LEVEL> <logger>: <message>"
        pattern = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} "
                             r"(INFO|ERROR|WARNING) [A-Za-z0-9_.]+: ")
        for line in lines:
            assert pattern.match(line), f"{who}: not the app's log format: {line!r}"
        return True

    assert shape(from_app, "the app"), "the app's own lines do not match the format"
    assert shape(from_cli, "the CLI"), "the CLI's lines do not match the same format"


def test_the_cli_and_the_app_share_one_log_file(tmp_path):
    """Not two logs that happen to look alike: the same file, appended to."""
    _prepared(tmp_path)
    _run(tmp_path, ["-c", BUILD], "shared.db")
    _, after_app = _run(tmp_path, ["-c", "pass"], "shared.db")

    assert "app.database.init_db" in after_app, "the app did not write its own lines"
    _, after_cli = _run(tmp_path, ["-m", "alembic", "upgrade", "head"], "shared.db")

    assert "app.database.init_db" in after_cli, "the app's lines vanished"
    assert "alembic.runtime.migration" in after_cli, "the CLI did not write to the same file"


def test_a_cli_migration_failure_reaches_the_app_log(tmp_path):
    """The CLI must not swallow a failure either."""
    db = _prepared(tmp_path)
    with sqlite3.connect(db) as con:
        con.execute("UPDATE alembic_version SET version_num='no_such_revision'")

    up, app_log = _run(tmp_path, ["-m", "alembic", "upgrade", "head"])

    assert up.returncode != 0, "the corrupted stamp was supposed to fail"
    assert "no_such_revision" in app_log, (
        f"the CLI failure is not in logs/app.log; it holds {app_log[-300:]!r}"
    )
