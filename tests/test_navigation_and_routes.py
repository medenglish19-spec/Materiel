import re
from pathlib import Path

from fastapi.testclient import TestClient
from jinja2 import Environment, FileSystemLoader, TemplateSyntaxError

from web import main

NAVIGATION_PATHS = {"/dashboard", "/equipment", "/equipment/numerical-status", "/meter-readings", "/meter-readings/operations", "/equipment-types", "/maintenance", "/faults-repairs", "/tires", "/batteries", "/fuel", "/missions", "/users", "/logout"}
PAGE_PATHS = {*NAVIGATION_PATHS, "/maintenance/periodic", "/maintenance/rules", "/tires/settings", "/tires/inventory", "/missions/drivers"}


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


def _registered_paths(app=None) -> set[str]:
    """مسارات التطبيق المسجّلة.

    FastAPI/Starlette 1.7 يغلّف `include_router` بكائن `_IncludedRouter` لا يملك
    `.path`، فنجمع المسارات من الراوترات المُضمَّنة مع بادئة سياق الإدراج.
    """
    target = app if app is not None else main.app
    paths: set[str] = set()
    pending = [(route, "") for route in target.routes]
    while pending:
        route, prefix = pending.pop()
        included = getattr(route, "original_router", None)
        if included is not None:
            context = getattr(route, "include_context", None)
            inner_prefix = prefix + (getattr(context, "prefix", "") or "")
            pending.extend((sub_route, inner_prefix) for sub_route in included.routes)
            continue
        path = getattr(route, "path", None)
        if path:
            paths.add(f"{prefix}{path}" if prefix else path)
    return paths


def test_registered_navigation_routes_are_real(monkeypatch):
    with _client(monkeypatch):
        paths = _registered_paths()
        assert NAVIGATION_PATHS <= paths


def test_base_navigation_contains_only_registered_internal_paths():
    html = Path("web/templates/base.html").read_text(encoding="utf-8")
    hrefs = re.findall(r'href=[\"\']([^\"\']+)[\"\']', html)
    internal_paths = {href.split("?", 1)[0].split("#", 1)[0] for href in hrefs if href.startswith("/") and not href.startswith("//") and not href.startswith("/static/")}
    registered_paths = _registered_paths()
    assert "#" not in hrefs
    assert internal_paths <= registered_paths


def test_shared_module_navigation_covers_page_groups_without_dropping_actions():
    html = Path("web/templates/base.html").read_text(encoding="utf-8")
    mapper = html.split("const moduleNavigation=(function(){", 1)[1].split("})();", 1)[0]
    registered_paths = _registered_paths()
    static_paths = set(re.findall(r"\['(/[^']*)','[^']*'", mapper))

    assert {
        "/equipment/analysis/operational",
        "/equipment-types/structure",
        "/maintenance/catalog-imports",
        "/meter-readings/operations",
        "/fuel/model-rates",
        "/batteries/equipment",
        "/missions/drivers",
    } <= static_paths
    assert all(_route_matches(path, registered_paths) for path in static_paths)
    assert "['/equipment-types','أنواع وطرازات العتاد',['admin']]" in mapper
    assert "['/maintenance/catalog-imports','استيراد الكتالوجات',['admin','fleet_manager']]" in mapper
    assert "[[uploadHref,'استيراد من مستند',['admin','fleet_manager']]]" in mapper
    assert "main.querySelectorAll('nav.module-nav,nav.module-tabs,nav.tires-nav,.ed-tabs')" in html
    assert ".navigation-actions" not in html.split("if(main&&moduleNavigation&&moduleNavigation.links.length){", 1)[1].split("if(main){", 1)[0]


def test_shared_module_navigation_uses_a_single_scrollable_rtl_row():
    html = Path("web/templates/base.html").read_text(encoding="utf-8")
    style = html.split("/* Shared fixed header:", 1)[1]

    assert "flex-wrap:nowrap" in style
    assert "overflow-x:auto" in style
    assert "white-space:nowrap" in style


def test_sidebar_and_topbar_share_the_selected_module_configuration():
    html = Path("web/templates/base.html").read_text(encoding="utf-8")

    assert "matches:function(path,candidate)" in html
    assert ".app-menu a[data-module-root]" in html
    assert "moduleNavigation.matches(p,link.dataset.moduleRoot)" in html
    assert "moduleNavigation.matches(p,item[0])" in html
    assert 'data-module-root="/equipment"' in html
    assert "activePath:activePath||null" in html


def test_desktop_navigation_reserves_header_space_and_sidebar_scrolls():
    html = Path("web/templates/base.html").read_text(encoding="utf-8")
    css = Path("static/css/style.css").read_text(encoding="utf-8")

    assert "overflow-y:auto" in html.split(".app-sidebar{", 1)[1].split("}", 1)[0]
    assert ".app-topbar .module-nav.app-module-nav[hidden]{display:flex!important;visibility:hidden" in html
    assert "@media (min-width:701px) and (max-height:720px)" in html
    assert "@media (min-width:701px){" in html
    assert ".app-topbar .module-nav.app-module-nav[hidden]{display:flex!important;visibility:hidden" in css
    assert 'data-em-action="undo"' in html
    assert 'data-em-action="redo"' in html
    assert 'data-em-action="save"' in html


def test_main_page_routes_are_registered(monkeypatch):
    """تعطيل المصادقة المؤقت أزال اشتراط الجلسة عن هذه الصفحات.

    نتحقّق هنا من تسجيل المسارات فقط. أمّا الوصول الفعلي بلا جلسة فيُغطّى
    في `tests/test_authenticated_pages.py` على قاعدة معزولة، حتى لا يلمس
    أي اختبار قاعدة `fleet_assets.db`.
    """
    with _client(monkeypatch):
        registered_paths = _registered_paths()
        for path in sorted(PAGE_PATHS):
            assert path in registered_paths, path


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
    registered_paths = _registered_paths()
    for path in _template_files():
        html = path.read_text(encoding="utf-8")
        targets = re.findall(r'(?:href|action)=[\"\']([^\"\']+)[\"\']', html)
        for target in targets:
            if target == "/equipment-types/models/":
                continue
            if not target.startswith("/") or target.startswith("//") or target.startswith("/static/"):
                continue
            assert _route_matches(target, registered_paths), f"{path}: {target}"

def test_login_page_remains_public(monkeypatch):
    with _client(monkeypatch) as client:
        response = client.get("/login")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert 'action="/login"' in response.text
