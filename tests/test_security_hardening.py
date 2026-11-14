"""Security regression tests for authentication, authorization and data safety.

These tests run with authentication *enabled* (``auth_enforced`` marker).  The
rest of the functional suite opts into the explicit development bypass so that
existing page tests keep exercising the UI; here every request must prove the
production behaviour.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core import config, data_paths
from app.core.config import settings
from app.core.csrf import CSRF_COOKIE_NAME, CSRF_HEADER_NAME
from app.core.security import create_access_token, hash_password
from app.database import uninstall_cleanup
from app.modules.users.models import User
from tests.test_authenticated_pages import (
    SEEDED_PASSWORD,
    SEEDED_USERNAME,
    _isolated_app,
)
from web import main

pytestmark = pytest.mark.auth_enforced

ROLE_PASSWORD = "Security@Test-2026"
ROLE_USERS = {
    "fleet_manager": "sec-fleet",
    "operator": "sec-operator",
    "viewer": "sec-viewer",
}
ALLOWED_FOR = {
    "operator": ("operator", "fleet_manager", "admin"),
    "fleet_manager": ("fleet_manager", "admin"),
}

# (method, path, minimum role) for every route that previously had no role
# checker.  Path ids are arbitrary: authorization is decided before any lookup.
ROUTE_CASES = [
    ("POST", "/api/faults-repairs/faults", "operator"),
    ("PATCH", "/api/faults-repairs/faults/1", "operator"),
    ("PATCH", "/api/faults-repairs/faults/1/status", "operator"),
    ("POST", "/api/faults-repairs/repairs", "operator"),
    ("PATCH", "/api/faults-repairs/repairs/1", "operator"),
    ("PATCH", "/api/faults-repairs/repairs/1/status", "operator"),
    ("POST", "/api/faults-repairs/repair-parts", "operator"),
    ("POST", "/api/faults-repairs/technician-interventions", "operator"),
    ("PATCH", "/api/faults-repairs/technician-interventions/1", "operator"),
    ("POST", "/api/faults-repairs/spare-parts", "fleet_manager"),
    ("PATCH", "/api/faults-repairs/spare-parts/1", "fleet_manager"),
    ("DELETE", "/api/faults-repairs/technician-interventions/1", "fleet_manager"),
    ("POST", "/api/faults-repairs/technicians", "fleet_manager"),
    ("PATCH", "/api/faults-repairs/technicians/1", "fleet_manager"),
    ("POST", "/api/spare-parts-requests", "operator"),
    ("PATCH", "/api/spare-parts-requests/1", "operator"),
    ("POST", "/api/spare-parts-requests/1/items", "operator"),
    ("PATCH", "/api/spare-parts-requests/items/1", "operator"),
    ("DELETE", "/api/spare-parts-requests/items/1", "operator"),
    ("DELETE", "/api/spare-parts-requests/1", "fleet_manager"),
    ("PATCH", "/api/spare-parts-requests/1/status", "fleet_manager"),
    ("DELETE", "/api/spare-parts-requests/items/1/receipt", "fleet_manager"),
    ("POST", "/api/spare-parts-movements", "fleet_manager"),
    ("PATCH", "/api/spare-parts-movements/1", "fleet_manager"),
    ("DELETE", "/api/spare-parts-movements/1", "fleet_manager"),
    ("POST", "/batteries", "operator"),
    ("POST", "/batteries/1/update", "operator"),
    ("POST", "/batteries/1/movements", "operator"),
    ("POST", "/batteries/settings", "fleet_manager"),
    ("POST", "/batteries/delete-selected", "fleet_manager"),
    ("POST", "/batteries/1/delete", "fleet_manager"),
    ("POST", "/fuel", "operator"),
    ("POST", "/fuel/1/update", "operator"),
    ("POST", "/fuel/1/delete", "operator"),
    ("POST", "/fuel/delete-selected", "operator"),
    ("POST", "/fuel/model-rates", "fleet_manager"),
    ("POST", "/fuel/model-rates/import", "fleet_manager"),
    ("POST", "/tires", "operator"),
    ("POST", "/tires/1/movements", "operator"),
    ("POST", "/tires/settings", "fleet_manager"),
    ("POST", "/tires/1/delete", "fleet_manager"),
    ("POST", "/tires/1/dispose", "fleet_manager"),
    ("POST", "/equipment/1/maintenance/create", "fleet_manager"),
    ("POST", "/equipment/1/maintenance/1/update", "fleet_manager"),
    ("POST", "/equipment/1/maintenance/1/delete", "fleet_manager"),
]

assert len(ROUTE_CASES) == 45


def _login(app: TestClient, username: str, password: str) -> tuple[TestClient, dict[str, str]]:
    client = TestClient(app, client=("127.0.0.1", 50000))
    response = client.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303), response.text
    token = client.cookies.get(CSRF_COOKIE_NAME)
    assert token, "login response must issue a CSRF cookie"
    return client, {CSRF_HEADER_NAME: token}


@pytest.fixture(scope="module")
def secure_env():
    with _isolated_app() as (app, TestingSession, ids):
        db = TestingSession()
        try:
            for role, username in ROLE_USERS.items():
                db.add(
                    User(
                        username=username,
                        full_name=f"Security {role}",
                        hashed_password=hash_password(ROLE_PASSWORD),
                        role=role,
                        is_active=True,
                    )
                )
            db.commit()
        finally:
            db.close()

        clients: dict[str, tuple[TestClient, dict[str, str]]] = {}
        clients["anonymous"] = (
            TestClient(app, client=("127.0.0.1", 50000)),
            {},
        )
        clients["admin"] = _login(app, SEEDED_USERNAME, SEEDED_PASSWORD)
        for role, username in ROLE_USERS.items():
            clients[role] = _login(app, username, ROLE_PASSWORD)

        try:
            yield app, TestingSession, ids, clients
        finally:
            for client, _headers in clients.values():
                client.close()


def _probe(client: TestClient, headers: dict[str, str], method: str, path: str):
    return client.request(
        method,
        path,
        headers=headers,
        json={},
        follow_redirects=False,
    )


@pytest.mark.parametrize(
    "method,path,min_role",
    ROUTE_CASES,
    ids=[f"{method} {path}" for method, path, _ in ROUTE_CASES],
)
def test_every_previously_open_write_route_enforces_least_privilege(
    secure_env, method: str, path: str, min_role: str
):
    _app, _Session, _ids, clients = secure_env

    anonymous, no_headers = clients["anonymous"]
    anonymous_response = _probe(anonymous, no_headers, method, path)
    assert anonymous_response.status_code == 401, (
        f"anonymous {method} {path} -> {anonymous_response.status_code}"
    )

    viewer, viewer_headers = clients["viewer"]
    viewer_response = _probe(viewer, viewer_headers, method, path)
    assert viewer_response.status_code == 403, (
        f"viewer {method} {path} -> {viewer_response.status_code}"
    )

    for role in ALLOWED_FOR[min_role]:
        client, headers = clients[role]
        response = _probe(client, headers, method, path)
        assert response.status_code not in (401, 403), (
            f"{role} must be allowed on {method} {path}; got {response.status_code}"
        )


def test_role_boundaries_do_not_escalate_operator_to_manager_routes(secure_env):
    _app, _Session, _ids, clients = secure_env
    operator, headers = clients["operator"]
    for method, path, min_role in ROUTE_CASES:
        if min_role != "fleet_manager":
            continue
        response = _probe(operator, headers, method, path)
        assert response.status_code == 403, (
            f"operator must be denied on manager route {method} {path}; "
            f"got {response.status_code}"
        )


def test_public_login_and_setup_stay_reachable_without_a_session(secure_env):
    _app, _Session, _ids, clients = secure_env
    anonymous, _ = clients["anonymous"]

    login_page = anonymous.get("/login")
    assert login_page.status_code == 200
    assert 'action="/login"' in login_page.text

    bad_login = anonymous.post(
        "/login",
        data={"username": "nobody", "password": "wrong"},
        follow_redirects=False,
    )
    assert bad_login.status_code == 401

    setup = anonymous.get("/setup", follow_redirects=False)
    assert setup.status_code == 303
    assert setup.headers["location"] == "/login"

    protected = anonymous.get("/api/me")
    assert protected.status_code == 401


def test_csrf_is_required_for_cookie_authenticated_writes(secure_env):
    _app, _Session, _ids, clients = secure_env
    operator, headers = clients["operator"]
    token = headers[CSRF_HEADER_NAME]

    missing = operator.post("/api/spare-parts-requests", json={})
    assert missing.status_code == 403
    assert "CSRF" in missing.text

    wrong = operator.post(
        "/api/spare-parts-requests",
        headers={CSRF_HEADER_NAME: "not-the-cookie-value"},
        json={},
    )
    assert wrong.status_code == 403

    accepted = operator.post(
        "/api/spare-parts-requests",
        headers={CSRF_HEADER_NAME: token},
        json={},
    )
    assert accepted.status_code != 403

    # Safe methods do not need a token.
    assert operator.get("/api/me").status_code == 200

    # A form field is accepted as well as the header (no JavaScript required).
    fleet, fleet_headers = clients["fleet_manager"]
    field_token = fleet_headers[CSRF_HEADER_NAME]
    form_response = fleet.post(
        "/tires/settings",
        data={"csrf_token": field_token},
    )
    assert form_response.status_code != 403


def test_session_cookie_and_csrf_cookie_flags_are_explicit(secure_env):
    _app, _Session, _ids, clients = secure_env
    anonymous, _ = clients["anonymous"]
    # This module-scoped client may already hold a CSRF cookie from earlier
    # probes; clear it so we observe the first-visit Set-Cookie behaviour.
    anonymous.cookies.clear()

    page = anonymous.get("/login")
    csrf_headers = page.headers.get_list("set-cookie")
    csrf_cookie = next(h for h in csrf_headers if h.startswith(f"{CSRF_COOKIE_NAME}="))
    assert "HttpOnly" not in csrf_cookie
    assert "SameSite=lax" in csrf_cookie
    assert "Path=/" in csrf_cookie

    login = anonymous.post(
        "/login",
        data={"username": SEEDED_USERNAME, "password": SEEDED_PASSWORD},
        follow_redirects=False,
    )
    session_cookie = next(
        h for h in login.headers.get_list("set-cookie")
        if h.startswith(f"{settings.SESSION_COOKIE_NAME}=")
    )
    assert "HttpOnly" in session_cookie
    assert "SameSite=lax" in session_cookie
    assert "Path=/" in session_cookie
    # Local HTTP installation: setting Secure here would break the packaged app.
    assert "; Secure" not in session_cookie


def test_password_change_invalidates_old_tokens_without_rotating_the_signing_key(
    secure_env, monkeypatch
):
    _app, TestingSession, _ids, _clients = secure_env

    db = TestingSession()
    try:
        db.add(
            User(
                username="sec-session-user",
                full_name="Session user",
                hashed_password=hash_password("OldPassword@123"),
                role="operator",
                is_active=True,
            )
        )
        db.commit()
    finally:
        db.close()

    client = TestClient(_app, client=("127.0.0.1", 50000))
    try:
        login = client.post(
            "/login",
            data={"username": "sec-session-user", "password": "OldPassword@123"},
            follow_redirects=False,
        )
        assert login.status_code in (302, 303)
        assert client.get("/api/me").status_code == 200
        signing_key = settings.SECRET_KEY

        db = TestingSession()
        try:
            user = db.query(User).filter_by(username="sec-session-user").one()
            user.hashed_password = hash_password("NewPassword@123")
            db.commit()
        finally:
            db.close()

        assert client.get("/api/me").status_code == 401
        assert settings.SECRET_KEY == signing_key

        # Tokens from older builds have no fingerprint and stay valid.
        legacy = create_access_token({"sub": "sec-session-user", "role": "operator"})
        client.cookies.set(settings.SESSION_COOKIE_NAME, legacy, path="/")
        assert client.get("/api/me").status_code == 200
    finally:
        client.close()


def test_uploads_require_authentication_and_reject_traversal(tmp_path, monkeypatch):
    data_root = tmp_path / "uploads"
    (data_root / "equipment").mkdir(parents=True)
    (data_root / "equipment" / "photo.png").write_bytes(b"private image")
    outside = tmp_path / "secret.key"
    outside.write_text("must not leak", encoding="utf-8")
    monkeypatch.setattr(main, "uploads_directory", lambda: data_root)

    app = main.create_app()
    with TestClient(app) as anonymous:
        assert anonymous.get("/static/uploads/equipment/photo.png").status_code == 401

    with TestClient(app) as client:
        login = client.post(
            "/login",
            data={"username": SEEDED_USERNAME, "password": SEEDED_PASSWORD},
            follow_redirects=False,
        )
        assert login.status_code in (302, 303)
        allowed = client.get("/static/uploads/equipment/photo.png")
        assert allowed.status_code == 200
        assert allowed.content == b"private image"

        traversal_paths = (
            "/static/uploads/%2e%2e/secret.key",
            "/static/uploads/%2e%2e%2fsecret.key",
            "/static/uploads/equipment/%2e%2e/%2e%2e/secret.key",
        )
        for path in traversal_paths:
            response = client.get(path)
            assert response.status_code == 404, f"traversal served: {path}"
            assert "must not leak" not in response.text

    with TestClient(app) as anonymous:
        assert anonymous.get("/static/css/style.css").status_code == 200


def test_previously_guarded_import_routes_still_deny_viewers(secure_env):
    _app, _Session, _ids, clients = secure_env
    viewer, headers = clients["viewer"]
    for path in (
        "/document-import/apply",
        "/document-import/preview",
        "/equipment/import/preview",
        "/spare-parts/catalog/import",
    ):
        response = viewer.post(path, headers=headers, json={}, follow_redirects=False)
        assert response.status_code == 403, path


def test_logging_redaction_hides_credentials_and_full_paths():
    from app.core.config import redact_database_url

    redacted = redact_database_url(
        "postgresql://alice:s3cr3t@db.internal:5432/fleet_assets?password=topsecret"
    )
    assert redacted == "postgresql://fleet_assets"
    for secret in ("alice", "s3cr3t", "db.internal", "topsecret"):
        assert secret not in redacted

    sqlite_path = redact_database_url("sqlite:///D:/MaterielData/fleet_assets.db")
    assert sqlite_path == "sqlite://fleet_assets.db"
    assert "MaterielData" not in sqlite_path


def test_dev_auth_bypass_is_explicit_loopback_only_and_never_in_production(monkeypatch):
    monkeypatch.setattr(config.sys, "frozen", False, raising=False)
    monkeypatch.delenv("DEV_DISABLE_AUTH", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.setenv("APP_HOST", "127.0.0.1")
    assert config.dev_auth_disabled() is False

    monkeypatch.setenv("DEV_DISABLE_AUTH", "true")
    assert config.dev_auth_disabled() is True

    monkeypatch.setenv("APP_HOST", "0.0.0.0")
    with pytest.raises(RuntimeError):
        config.dev_auth_disabled()

    monkeypatch.setenv("APP_HOST", "127.0.0.1")
    monkeypatch.setenv("APP_ENV", "production")
    assert config.dev_auth_disabled() is False

    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setattr(config.sys, "frozen", True, raising=False)
    assert config.dev_auth_disabled() is False


def test_production_refuses_the_published_default_signing_key(monkeypatch):
    monkeypatch.setattr(config.sys, "frozen", False, raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError):
        config.application_secret_key()

    monkeypatch.setenv("SECRET_KEY", "x" * 64)
    assert config.application_secret_key() == "x" * 64


def test_packaged_data_directory_survives_a_missing_sidecar(tmp_path, monkeypatch):
    executable_dir = tmp_path / "app"
    executable_dir.mkdir()
    executable = executable_dir / "Materiel.exe"
    executable.touch()

    monkeypatch.delenv("MATERIEL_DATA_DIR", raising=False)
    monkeypatch.setattr(data_paths, "registry_data_directory", lambda: None)
    monkeypatch.setattr(data_paths, "discovered_data_directory", lambda: None)
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "ProgramData"))
    assert data_paths.packaged_data_directory(executable) == (
        tmp_path / "ProgramData" / "Materiel" / "data"
    )

    registry_data = tmp_path / "D" / "MaterielData"
    registry_data.mkdir(parents=True)
    monkeypatch.setattr(data_paths, "registry_data_directory", lambda: registry_data)
    assert data_paths.packaged_data_directory(executable) == registry_data

    sidecar_data = tmp_path / "custom-data"
    sidecar_data.mkdir()
    (executable_dir / "materiel-data-dir.txt").write_text(
        str(sidecar_data), encoding="utf-8"
    )
    assert data_paths.packaged_data_directory(executable) == sidecar_data


def test_drive_discovery_finds_an_existing_data_folder(tmp_path, monkeypatch):
    drive_root = tmp_path / "D"
    data_dir = drive_root / "MaterielData"
    data_dir.mkdir(parents=True)
    (data_dir / "fleet_assets.db").write_bytes(b"SQLite format 3\x00")

    monkeypatch.setattr(data_paths, "registry_data_directory", lambda: None)
    monkeypatch.setattr(data_paths, "_drive_roots", lambda: [drive_root])
    monkeypatch.setenv("PROGRAMDATA", str(tmp_path / "empty-programdata"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "empty-localappdata"))
    assert data_paths.discovered_data_directory() == data_dir


def test_windows_installer_never_grants_users_modify_and_uses_safe_icacls_order():
    installer = Path(__file__).resolve().parents[1] / "windows" / "materiel.iss"
    content = installer.read_text(encoding="utf-8")
    lowered = content.lower()

    assert "users-modify" not in lowered
    assert "hkcU" not in lowered and "HKCU" in content  # registry lookup survives
    assert "Software\\Materiel" in content
    assert "ResetChildAcls" in content
    assert "/reset" in content

    # The original bug: /inheritance:r together with /T leaves files protected
    # with an empty DACL.  No single icacls invocation may combine them.
    for number, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        if stripped.startswith(("{", "//", ";")):
            continue  # documentation comment, not an executed command
        if "icacls" in line.lower() or "/inheritance:r" in line:
            assert not (
                "/inheritance:r" in line and "/T" in line
            ), f"unsafe icacls combination at materiel.iss:{number}"
