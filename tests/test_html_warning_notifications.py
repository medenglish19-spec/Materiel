from fastapi import HTTPException
from fastapi.testclient import TestClient

from web import main


def _client(monkeypatch):
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "create_default_admin", lambda: None)
    app = main.create_app()

    @app.post("/test-warning")
    def test_warning():
        raise HTTPException(status_code=409, detail="لا يمكن تنفيذ العملية؛ يجب إكمال الإجراء المطلوب أولًا")

    @app.post("/test-server-error")
    def test_server_error():
        raise HTTPException(status_code=500, detail="تعذر إكمال العملية")

    return TestClient(app)


def test_html_post_error_redirects_with_guided_warning(monkeypatch):
    with _client(monkeypatch) as client:
        response = client.post(
            "/test-warning",
            headers={"Accept": "text/html", "Referer": "http://testserver/equipment/12/edit"},
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert response.headers["location"].startswith("/equipment/12/edit?notice_type=warning&notice=")
    assert "%D9%84%D8%A7" in response.headers["location"]


def test_api_error_keeps_json_response(monkeypatch):
    with _client(monkeypatch) as client:
        response = client.post("/test-warning", headers={"Accept": "application/json"})
    assert response.status_code == 409
    assert response.json()["detail"].startswith("لا يمكن تنفيذ العملية")


def test_html_server_error_redirects_as_a_centered_error_notice(monkeypatch):
    with _client(monkeypatch) as client:
        response = client.post(
            "/test-server-error",
            headers={"Accept": "text/html", "Referer": "http://testserver/tires"},
            follow_redirects=False,
        )
    assert response.status_code == 303
    assert response.headers["location"].startswith("/tires?notice_type=danger&notice=")


def test_base_notice_modal_is_centered_and_accessible():
    from pathlib import Path

    base_template = Path(__file__).parents[1] / "web" / "templates" / "base.html"
    source = base_template.read_text(encoding="utf-8")
    assert ".materiel-notice-backdrop{position:fixed" in source
    assert "place-items:center" in source
    assert "box.setAttribute('role','alertdialog')" in source
    assert "box.setAttribute('aria-modal','true')" in source
