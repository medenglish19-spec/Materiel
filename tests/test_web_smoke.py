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

    from app.core import branding

    (tmp_path / "config.json").write_text(json.dumps({
        "institution_name": "مؤسسة الاختبار",
        "description": "نص تعريفي مخصص",
        "developer_name": "فريق الاختبار",
        "version": "2.4",
        "logo_file": "logo.png",
    }, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "logo.png").write_bytes(b"test-logo")
    monkeypatch.setattr(branding, "customization_directory", lambda: tmp_path)

    with _client(monkeypatch) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert "مؤسسة الاختبار" in response.text
    assert "نص تعريفي مخصص" in response.text
    assert "فريق الاختبار" in response.text
    assert "الإصدار 2.4" in response.text
    assert "data:image/png;base64," in response.text


def test_packaged_splash_reads_release_assets_and_ignores_user_data(monkeypatch, tmp_path):
    import base64
    from io import BytesIO
    import json

    from app.core import branding
    from PIL import Image

    install_dir = tmp_path / "installed-program"
    bundle_dir = install_dir / "_internal"
    splash_dir = bundle_dir / "splash-screen"
    splash_dir.mkdir(parents=True)
    data_dir = tmp_path / "MaterielData"
    user_splash_dir = data_dir / "splash-screen"
    user_splash_dir.mkdir(parents=True)
    executable = install_dir / "Materiel.exe"
    executable.touch()
    config_path = splash_dir / "config.json"
    logo_path = splash_dir / "logo.png"
    user_config_path = user_splash_dir / "config.json"
    user_logo_path = user_splash_dir / "logo.png"
    def png_bytes(color):
        buffer = BytesIO()
        Image.new("RGB", (2, 2), color).save(buffer, format="PNG")
        return buffer.getvalue()

    first_logo = png_bytes((190, 30, 30))
    user_logo = png_bytes((20, 80, 200))
    logo_path.write_bytes(first_logo)

    def write_branding(institution_name, description, logo_file="logo.png"):
        config_path.write_text(json.dumps({
            "institution_name": institution_name,
            "description": description,
            "developer_name": "فريق الاختبار",
            "version": "1.0.0",
            "logo_file": logo_file,
        }, ensure_ascii=False), encoding="utf-8")

    write_branding("مؤسسة الإصدار الأول", "نص الإصدار الأول")
    user_config_path.write_text(json.dumps({
        "institution_name": "بيانات المستخدم",
        "description": "يجب تجاهلها في النسخة المثبتة",
        "developer_name": "مستخدم",
        "version": "9.9.9",
        "logo_file": "logo.png",
    }, ensure_ascii=False), encoding="utf-8")
    user_logo_path.write_bytes(user_logo)
    monkeypatch.setattr(branding.sys, "executable", str(executable))
    monkeypatch.setattr(branding.sys, "frozen", True, raising=False)
    monkeypatch.setattr(branding.sys, "_MEIPASS", str(bundle_dir), raising=False)

    with _client(monkeypatch) as client:
        first = client.get("/")
        assert "مؤسسة الإصدار الأول" in first.text
        assert f"data:image/png;base64,{base64.b64encode(first_logo).decode('ascii')}" in first.text
        assert "بيانات المستخدم" not in first.text

        # A newly built release carries its own changed branding assets.
        next_bundle = tmp_path / "next-release" / "_internal"
        next_splash_dir = next_bundle / "splash-screen"
        next_splash_dir.mkdir(parents=True)
        next_config_path = next_splash_dir / "config.json"
        next_logo_path = next_splash_dir / "logo.png"
        next_config_path.write_text(json.dumps({
            "institution_name": "مؤسسة الإصدار التالي",
            "description": "نص الإصدار التالي",
            "developer_name": "فريق الاختبار",
            "version": "1.1.0",
            "logo_file": "logo.png",
        }, ensure_ascii=False), encoding="utf-8")
        next_logo = png_bytes((20, 80, 200))
        next_logo_path.write_bytes(next_logo)
        monkeypatch.setattr(branding.sys, "_MEIPASS", str(next_bundle), raising=False)
        updated = client.get("/")

    assert "مؤسسة الإصدار التالي" in updated.text
    assert "نص الإصدار التالي" in updated.text
    assert f"data:image/png;base64,{base64.b64encode(next_logo).decode('ascii')}" in updated.text


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
