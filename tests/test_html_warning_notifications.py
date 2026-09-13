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
