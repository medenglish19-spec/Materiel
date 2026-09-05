import re
from pathlib import Path

from fastapi.testclient import TestClient
from jinja2 import Environment, FileSystemLoader, TemplateSyntaxError

from web import main

NAVIGATION_PATHS = {"/dashboard", "/equipment", "/equipment/numerical-status", "/meter-readings", "/meter-readings/operations", "/equipment-types", "/maintenance", "/faults-repairs", "/tires", "/batteries", "/fuel", "/missions", "/users", "/logout"}
PAGE_PATHS = {*NAVIGATION_PATHS, "/maintenance/periodic", "/maintenance/rules", "/tires/settings", "/tires/inventory", "/tires/positions"}


def _client(monkeypatch):
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "create_default_admin", lambda: None)
    return TestClient(main.create_app())


def _route_matches(path: str, registered_paths: set[str]) -> bool:
    raw_candidate = re.sub(r"{{.*?}}", "1", path).split("?", 1)[0].split("#", 1)[0]
    candidate = raw_candidate.rstrip("/") or "/"
    candidate_parts = [part for part in candidate.split("/") if part]
    for route in registered_paths:
        route_parts = [part for part in route.rstrip("/").split("/") if part]
        if len(route_parts) != len(candidate_parts):
            continue
        if all(
            route_part.startswith("{") and route_part.endswith("}")
            or route_part == candidate_part
            for route_part, candidate_part in zip(route_parts, candidate_parts)
        ):
            return True

    # A Jinja template may expose a base URL ending with '/' while the
    # rendered value supplies the final dynamic path parameter.
    if raw_candidate.endswith("/") and candidate_parts:
        for route in registered_paths:
            route_parts = [part for part in route.rstrip("/").split("/") if part]
            if (
                len(route_parts) == len(candidate_parts) + 1
                and route_parts[:-1] == candidate_parts
                and route_parts[-1].startswith("{")
                and route_parts[-1].endswith("}")
            ):
                return True

    return not candidate_parts and "/" in registered_paths


def _template_files():
    return [Path("web/templates/base.html"), *Path("app").glob("modules/**/templates/*.html")]


def test_registered_navigation_routes_are_real(monkeypatch):
    with _client(monkeypatch):
        paths = {route.path for route in main.app.routes}
        assert NAVIGATION_PATHS <= paths


def test_base_navigation_contains_only_registered_internal_paths():
    html = Path("web/templates/base.html").read_text(encoding="utf-8")
    hrefs = re.findall(r'href=[\"\']([^\"\']+)[\"\']', html)
    internal_paths = {href.split("?", 1)[0].split("#", 1)[0] for href in hrefs if href.startswith("/") and not href.startswith("//") and not href.startswith("/static/")}
    registered_paths = {route.path for route in main.app.routes}
    assert "#" not in hrefs
    assert internal_paths <= registered_paths


def test_main_page_routes_exist_and_are_protected(monkeypatch):
    with _client(monkeypatch) as client:
        registered_paths = {route.path for route in main.app.routes}
        for path in sorted(PAGE_PATHS):
            assert path in registered_paths, path
            response = client.get(path, follow_redirects=False)
            assert response.status_code in {302, 303, 401, 403}, path
            if response.status_code in {302, 303}:
                assert response.headers.get("location", "").startswith("/login"), path


def test_logout_remains_public_and_redirects_to_login(monkeypatch):
    with _client(monkeypatch) as client:
        response = client.get("/logout", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/login"


def test_all_html_templates_have_valid_jinja_syntax():
    root = Path("app")
    env = Environment(loader=FileSystemLoader(str(root)))
    for path in sorted(root.glob("modules/**/templates/*.html")):
        try:
            env.parse(path.read_text(encoding="utf-8"))
        except TemplateSyntaxError as exc:
            raise AssertionError(f"Invalid Jinja template: {path}: {exc}") from exc


def test_no_placeholder_links_or_actions_exist_in_html_templates():
    for path in _template_files():
        html = path.read_text(encoding="utf-8")
        assert not re.search(r'href=[\"\']#[\"\']', html), path
        assert not re.search(r'action=[\"\']#[\"\']', html), path


def test_template_internal_links_and_form_actions_match_registered_routes():
    registered_paths = {route.path for route in main.app.routes}
    for path in _template_files():
        html = path.read_text(encoding="utf-8")
        targets = re.findall(r'(?:href|action)=[\"\']([^\"\']+)[\"\']', html)
        for target in targets:
            if not target.startswith("/") or target.startswith("//") or target.startswith("/static/"):
                continue
            assert _route_matches(target, registered_paths), f"{path}: {target}"


def test_login_page_remains_public(monkeypatch):
    with _client(monkeypatch) as client:
        response = client.get("/login")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert 'action="/login"' in response.text
