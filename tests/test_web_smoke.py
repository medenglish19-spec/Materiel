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


def test_root_renders_splash_and_offers_dashboard_when_auth_is_disabled(monkeypatch):
    """تظهر شاشة الافتتاحية ويقود زر الدخول إلى الوجهة المناسبة."""
    with _client(monkeypatch) as client:
        response = client.get("/", follow_redirects=False)
    assert response.status_code == 200
    assert "نظام تسيير و محاسبة العتاد" in response.text
    assert "اسم المؤسسة" in response.text
    assert 'href="/dashboard"' in response.text


def test_splash_content_can_be_changed_without_rebuilding(monkeypatch, tmp_path):
    import json

    from web import splash_screen

    (tmp_path / "config.json").write_text(json.dumps({
        "institution_name": "مؤسسة الاختبار",
        "description": "نص تعريفي مخصص",
        "developer_name": "فريق الاختبار",
        "version": "2.4",
        "logo_file": "logo.png",
    }, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "logo.png").write_bytes(b"test-logo")
    monkeypatch.setattr(splash_screen, "customization_directory", lambda: tmp_path)

    with _client(monkeypatch) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "مؤسسة الاختبار" in response.text
    assert "نص تعريفي مخصص" in response.text
    assert "فريق الاختبار" in response.text
    assert "الإصدار 2.4" in response.text
    assert "data:image/png;base64," in response.text


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
