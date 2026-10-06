"""The spare-parts movement pages must be reachable.

``/spare-parts-return`` answered 404 while ``/spare-parts-distribution`` worked,
even though both were declared the same way in the same router and the sidebar
linked to it. The route was registered by a commit made after the running
worker started, so the process never had it -- these tests pin the path against
a freshly built app, which is where the difference is visible.

web/main.py also used to register the three movement pages twice: once through
include_router and again with add_api_route. One registration is enough, and
the tests below fail if a page ever ends up served twice.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import session as session_module
from app.database.base import Base

ROOT = Path(__file__).resolve().parents[1]
PAGE = "/spare-parts-return"
BASE_TEMPLATE = ROOT / "web" / "templates" / "base.html"

USERNAME = "movements-page-reader"
PASSWORD = "Test@12345"


@pytest.fixture(scope="module")
def client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False)
    Base.metadata.create_all(engine)

    db = TestingSession()
    try:
        from app.core.security import hash_password
        from app.modules.users.models import User

        db.add(User(username=USERNAME, full_name="قارئ صفحات الغيار",
                    hashed_password=hash_password(PASSWORD), role="admin"))
        db.commit()
    finally:
        db.close()

    def override_get_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(session_module, "SessionLocal", TestingSession)

        from web import main

        patch.setattr(main, "init_db", lambda: None)
        patch.setattr(main, "create_default_admin", lambda: None)

        app = main.create_app()
        app.dependency_overrides[session_module.get_db] = override_get_db

        with TestClient(app) as c:
            response = c.post("/login", data={"username": USERNAME, "password": PASSWORD},
                              follow_redirects=False)
            assert response.status_code in (302, 303), "فشل تسجيل الدخول"
            yield c


def _walk(routes):
    """Every endpoint in the route table, included routers included.

    This FastAPI keeps ``include_router`` results as ``_IncludedRouter``
    wrappers that carry no ``.path``, so a flat scan of ``app.routes`` sees
    almost nothing and silently passes anything it cannot look at.
    """
    for route in routes:
        yield route
        original = getattr(route, "original_router", None)
        if original is not None:
            yield from _walk(original.routes)


def _build_app():
    from app.database import model_registry  # noqa: F401
    from web import main

    return main.create_app()


def test_the_return_page_is_not_a_404(client):
    response = client.get(PAGE, follow_redirects=False)

    assert response.status_code != 404, f"{PAGE} is not registered at all"
    assert response.status_code == 200, (
        f"{PAGE} answered {response.status_code}, not 200: {response.text[:300]}"
    )


def test_the_return_page_shows_its_title(client):
    body = client.get(PAGE).text

    assert "إرجاع الغيار" in body, "the page does not carry the إرجاع الغيار title"


def test_the_return_page_is_rendered_from_its_own_template(client):
    """It must be return.html, not another page that happens to answer 200."""
    response = client.get(PAGE)

    assert "text/html" in response.headers.get("content-type", "")
    assert 'id="receipt"' in response.text, "the page must select a received item"
    assert 'id="source"' not in response.text, "returns must not require a distribution source"


@pytest.mark.parametrize("path", [
    PAGE,
    "/spare-parts-distribution",
    "/spare-parts-history/{request_item_id}",
])
def test_each_movement_page_is_registered_exactly_once(path):
    """No page may end up with two routes serving the same URL."""
    hits = [r for r in _walk(_build_app().routes) if getattr(r, "path", None) == path]

    assert len(hits) == 1, (
        f"{path} is served by {len(hits)} routes: {[getattr(h, 'name', None) for h in hits]}"
    )


def test_the_sidebar_link_points_at_the_real_path():
    """The nav href and the route must agree, or the link 404s for the user."""
    text = BASE_TEMPLATE.read_text(encoding="utf-8")

    assert f'href="{PAGE}"' in text, f"the sidebar does not link to {PAGE}"
