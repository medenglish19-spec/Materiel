import json

from fastapi.testclient import TestClient

from app.core import branding
from web import main


def test_supervisor_from_splash_config_appears_before_entry_button(monkeypatch, tmp_path):
    config = {
        "institution_name": "مؤسسة الاختبار",
        "description": "رسالة ترحيب",
        "developer_name": "فريق الاختبار",
        "supervisor_name": "المشرف التجريبي",
        "version": "2.0",
        "logo_file": "logo.png",
    }
    (tmp_path / "config.json").write_text(
        json.dumps(config, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setattr(branding, "customization_directory", lambda: tmp_path)
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "create_default_admin", lambda: None)

    with TestClient(main.create_app()) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "المطور: <strong>فريق الاختبار</strong>" in response.text
    assert "المشرف: <strong>المشرف التجريبي</strong>" in response.text
    assert response.text.index('class="credits"') < response.text.index('class="start"')
