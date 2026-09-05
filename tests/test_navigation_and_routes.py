import re
from pathlib import Path

from fastapi.testclient import TestClient

from web import main


NAVIGATION_PATHS = {
    "/dashboard",
    "/equipment",
    "/equipment/numerical-status",
    "/meter-readings",
    "/meter-readings/operations",
    "/equipment-types",
    "/maintenance",
    "/faults-repairs",
    "/tires",
    "/batteries",
    "/fuel",
    "/missions",
    "/users",
    "/logout",
}


def _client(monkeypatch):
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "create_default_admin", lambda: None)
    return TestClient(main.create_app())


def test_registered_navigation_routes_are_real(monkeypatch):
    with _client(monkeypatch):
        paths = {route.path for route in main.app.routes}
        assert NAVIGATION_PATHS <= paths


def test_base_navigation_contains_only_registered_internal_paths():
    html = Path("web/templates/base.html").read_text(encoding="utf-8")
    hrefs = re.findall(r'href=[\"\']([^\"\']+)[\"\']', html)
    internal_paths = {
        href.split("?", 1)[0].split("#", 1)[0]
        for href in hrefs
        if href.startswith("/") and not href.startswith("//")
    }
    registered_paths = {route.path for route in main.app.routes}
    ignored_prefixes = ("/static",)

    assert "#" not in hrefs
    assert internal_paths - set(ignored_prefixes) <= registered_paths | {
        path for path in registered_paths if path.endswith("/")
    }


def test_protected_navigation_pages_redirect_to_login_when_unauthenticated(monkeypatch):
    with _client(monkeypatch) as client:
        for path in sorted(NAVIGATION_PATHS - {"/logout"}):
            response = client.get(path, follow_redirects=False)
            assert response.status_code in {302, 303}, path
            assert response.headers.get("location", "").startswith("/login"), path


def test_login_page_remains_public(monkeypatch):
    with _client(monkeypatch) as client:
        response = client.get("/login")
        assert response.status_code == 200
        assert 'action="/login"' in response.text
