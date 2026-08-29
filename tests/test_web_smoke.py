from fastapi.testclient import TestClient

from web import main


def _client(monkeypatch):
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "create_default_admin", lambda: None)
    return TestClient(main.create_app())


def test_health_endpoint(monkeypatch):
    with _client(monkeypatch) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_redirects_to_login_without_session(monkeypatch):
    with _client(monkeypatch) as client:
        response = client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/login"


def test_login_page_renders_html(monkeypatch):
    with _client(monkeypatch) as client:
        response = client.get("/login")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "تسجيل الدخول" in response.text
    assert 'action="/login"' in response.text


def test_login_page_can_load_static_css(monkeypatch):
    with _client(monkeypatch) as client:
        response = client.get("/static/css/style.css")
    assert response.status_code == 200
    assert ".login-body" in response.text
