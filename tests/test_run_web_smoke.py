import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import Mock
from urllib.request import urlopen

import run_web



def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def test_official_run_web_starts_and_serves_login(tmp_path):
    port = _free_port()
    env = os.environ.copy()
    env.update(
        {
            "DATABASE_URL": f"sqlite:///{tmp_path / 'smoke.db'}",
            "APP_HOST": "127.0.0.1",
            "APP_PORT": str(port),
            "UVICORN_RELOAD": "false",
            "SECRET_KEY": "ci-smoke-secret",
        }
    )
    process = subprocess.Popen(
        [sys.executable, "run_web.py"],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        deadline = time.monotonic() + 15
        last_error = None
        while time.monotonic() < deadline:
            try:
                with urlopen(f"http://127.0.0.1:{port}/login", timeout=2) as response:
                    assert response.status in {200, 303}
                    return
            except Exception as exc:  # server may still be running startup migrations
                last_error = exc
                if process.poll() is not None:
                    output = process.stdout.read() if process.stdout else ""
                    raise AssertionError(f"run_web.py exited early: {output}") from exc
                time.sleep(0.25)
        raise AssertionError(f"run_web.py did not become ready: {last_error}")
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def test_packaged_mutex_matches_installer_mutex():
    identity = run_web._identity()

    assert f"Local\\{identity}" == "Local\\Materiel"


def test_shutdown_event_name_is_stable_for_installed_app():
    identity = run_web._identity()

    assert run_web._shutdown_event_name(identity) == "Global\\Materiel-shutdown"
    assert run_web._legacy_shutdown_event_name(identity) == "Local\\Materiel-shutdown"


def test_installed_app_has_a_cross_session_mutex_for_safe_updates():
    identity = run_web._identity()

    assert run_web._global_mutex_name(identity) == "Global\\Materiel"


def test_busy_preferred_port_uses_a_different_listening_socket():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as blocker:
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        blocked_port = blocker.getsockname()[1]

        server_socket = run_web._bind_server_socket("127.0.0.1", blocked_port)
        try:
            assert server_socket.getsockname()[1] != blocked_port
            assert server_socket.getsockname()[1] > 0
        finally:
            server_socket.close()


def test_browser_can_be_disabled_for_installer_smoke_tests(monkeypatch):
    monkeypatch.setenv("MATERIEL_NO_BROWSER", "1")
    browser_open = Mock()
    monkeypatch.setattr(run_web.webbrowser, "open", browser_open)

    assert run_web._open_url("127.0.0.1", 8000)
    browser_open.assert_not_called()
