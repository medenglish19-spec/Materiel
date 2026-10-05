"""The CI health step has to be wired in, and it has to be able to fail.

Two things can silently go wrong here. The workflow can lose the step -- CI
stays green because nobody notices the database is never checked. Or the step can
be wired but never fail, because it inspects the wrong file. So one test reads
the workflow to prove the step is there, and one runs the same command CI runs
against a database that has been broken on purpose.

The command is not "alembic upgrade head". The migration chain starts from a 0006
baseline that expects its tables to exist, so on an empty file it dies with
"no such table: equipment_models". A new install is built by create_all + stamp
head, and that is what CI has to reproduce.
"""

import re
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

WORKFLOW = ROOT / ".github/workflows/python-package-conda.yml"


@pytest.fixture(scope="module")
def workflow_text() -> str:
    assert WORKFLOW.is_file(), f"the workflow is gone: {WORKFLOW}"
    return WORKFLOW.read_text(encoding="utf-8")


def test_ci_checks_database_health(workflow_text):
    assert "scripts/check_db_health.py" in workflow_text, (
        "CI no longer checks database health -- a migration that orphans rows "
        "would ship silently"
    )


def test_the_health_check_runs_before_the_tests(workflow_text):
    """After the tests it would report on a build nobody is looking at."""
    check_at = workflow_text.find("scripts/check_db_health.py")
    tests_at = workflow_text.find("pytest -q")
    assert check_at != -1 and tests_at != -1
    assert check_at < tests_at, (
        "the health check runs after the tests, so a failure is buried"
    )


def test_the_health_check_uses_a_fresh_database_not_the_committed_one(workflow_text):
    """The committed fleet_assets.db is not in git, and must not be the subject."""
    step = workflow_text[workflow_text.find("ci_health_check"):]
    assert "DATABASE_URL: sqlite:///./ci_health_check.db" in workflow_text, (
        "the health step must build its own database"
    )
    assert "check_db_health.py ci_health_check.db" in step, (
        "the check is pointed at something other than the database just built"
    )


def _run_lines(workflow_text: str) -> str:
    """Only the run: blocks, so comments explaining a choice are not read as it."""
    blocks = re.findall(r"run: (?:.*\n(?: {8,}.*\n?)*)", workflow_text)
    return "\n".join(blocks)


def test_ci_builds_the_database_the_way_a_new_install_does(workflow_text):
    """create_all + stamp head, not an upgrade from nothing."""
    assert "init_db" in _run_lines(workflow_text), (
        "CI builds the database differently from a real new install, so it is "
        "not testing the path users take"
    )
    assert "alembic upgrade head" not in _run_lines(workflow_text), (
        "the chain starts from a 0006 baseline and cannot upgrade an empty file"
    )


def test_a_freshly_built_database_is_healthy(tmp_path):
    """The same two commands CI runs, in the same order."""
    db = tmp_path / "ci_health_check.db"
    url = f"sqlite:///{db.as_posix()}"
    env = {"DATABASE_URL": url, "PYTHONIOENCODING": "utf-8",
           "PATH": __import__("os").environ.get("PATH", "")}

    build = subprocess.run(
        [sys.executable, "-c", "from app.database.init_db import init_db; init_db()"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        errors="replace", env={**__import__("os").environ, **env},
    )
    assert build.returncode == 0, build.stderr[-2000:]

    check = subprocess.run(
        [sys.executable, "scripts/check_db_health.py", str(db)],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        errors="replace", env={**__import__("os").environ, **env},
    )
    assert check.returncode == 0, (
        f"a freshly built database is not healthy:\n{check.stdout}"
    )


def test_the_ci_step_would_fail_on_a_broken_database(tmp_path):
    """Otherwise the step is decoration."""
    db = tmp_path / "broken.db"
    url = f"sqlite:///{db.as_posix()}"
    env = {**__import__("os").environ, "DATABASE_URL": url,
           "PYTHONIOENCODING": "utf-8"}

    build = subprocess.run(
        [sys.executable, "-c", "from app.database.init_db import init_db; init_db()"],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        errors="replace", env=env,
    )
    assert build.returncode == 0, build.stderr[-2000:]

    # the fault stage13 exists to prevent: a link to a type that never existed
    con = sqlite3.connect(db)
    try:
        con.execute("PRAGMA foreign_keys=OFF")
        con.execute(
            "INSERT INTO equipment_type_spec_definitions "
            "(equipment_type_id, spec_definition_id) VALUES (99999, 99999)")
        con.commit()
    finally:
        con.close()

    check = subprocess.run(
        [sys.executable, "scripts/check_db_health.py", str(db)],
        cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
        errors="replace", env=env,
    )
    assert check.returncode != 0, (
        "an orphaned row did not fail the health check -- the CI step is "
        "decorative and would pass on a corrupt database"
    )
    assert "orphan" in check.stdout, check.stdout


def test_the_workflow_is_valid_yaml():
    try:
        import yaml
    except ImportError:
        pytest.skip("pyyaml is not installed")

    parsed = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    steps = parsed["jobs"]["test"]["steps"]
    names = [s.get("name", "") for s in steps]
    assert any("health" in n.lower() for n in names), names


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))