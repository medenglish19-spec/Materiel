"""عقود تحذيرات ما قبل النشر (core/config.py::security_warnings).

قرار المشروع: **لا نغيّر كلمة مرور المدير ولا نرفض الإقلاع**. مقصودٌ أن يبقى
`admin/Admin@123` صالحاً محلياً، لكن ألا يمرّ دون تنبيه مكتوب في السجل. هذه
الاختبارات تثبّت السلوك حتى لا يصير التحذير صامتاً أو ازدواجياً.
"""

import logging
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core import config as config_module
from app.core.config import DEFAULT_ADMIN_PASSWORD, DEFAULT_SECRET_KEY, security_warnings
from app.core.security import hash_password
from app.database import model_registry  # noqa: F401  (يسجّل كل النماذج قبل create_all)
from app.database.base import Base


def _user_db(path: Path, password: str | None) -> None:
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        if password is None:
            from app.modules.users.models import User

            db.add(
                User(
                    username="someone-else",
                    full_name="مستخدم",
                    hashed_password=hash_password("Whatever@123"),
                    role="admin",
                )
            )
        else:
            from app.modules.users.models import User

            db.add(
                User(
                    username="admin",
                    full_name="مدير",
                    hashed_password=hash_password(password),
                    role="admin",
                )
            )
        db.commit()
    finally:
        db.close()
        engine.dispose()


def test_default_secret_key_is_reported(monkeypatch):
    monkeypatch.setattr(config_module.settings, "SECRET_KEY", DEFAULT_SECRET_KEY)

    warnings = security_warnings()

    assert any("SECRET_KEY" in w for w in warnings)
    assert "الإقلاع" not in "".join(warnings)  # تحذير فقط، لا يمنع التشغيل


def test_a_custom_secret_key_produces_no_secret_warning(monkeypatch, tmp_path):
    monkeypatch.setattr(config_module.settings, "SECRET_KEY", "a-real-random-secret")
    database = tmp_path / "fleet.db"
    _user_db(database, "SomethingElse@123")

    warnings = security_warnings(str(database))

    assert not any("SECRET_KEY" in w for w in warnings)


def test_default_admin_password_is_reported_from_a_real_database(monkeypatch, tmp_path):
    monkeypatch.setattr(config_module.settings, "SECRET_KEY", "a-real-random-secret")
    database = tmp_path / "fleet.db"
    _user_db(database, DEFAULT_ADMIN_PASSWORD)

    warnings = security_warnings(str(database))

    assert any(DEFAULT_ADMIN_PASSWORD in w for w in warnings)


def test_changed_admin_password_is_not_reported(monkeypatch, tmp_path):
    monkeypatch.setattr(config_module.settings, "SECRET_KEY", "a-real-random-secret")
    database = tmp_path / "fleet.db"
    _user_db(database, "SomethingElse@123")

    warnings = security_warnings(str(database))

    assert warnings == []


def test_missing_database_warns_that_admin_will_be_seeded(tmp_path):
    database = tmp_path / "not-created-yet.db"

    warnings = security_warnings(str(database))

    assert any(DEFAULT_ADMIN_PASSWORD in w for w in warnings)
    assert any("admin" in w for w in warnings)


def test_a_database_without_an_admin_user_is_not_reported(monkeypatch, tmp_path):
    monkeypatch.setattr(config_module.settings, "SECRET_KEY", "a-real-random-secret")
    database = tmp_path / "fleet.db"
    _user_db(database, None)

    assert security_warnings(str(database)) == []


def test_unreadable_database_does_not_raise(tmp_path):
    """فحص أمني لا يجوز أن يمنع الإقلاع (قاعدة مقفلة/تالفة/غير مخوصة)."""
    broken = tmp_path / "broken.db"
    broken.write_text("this is not a sqlite database", encoding="utf-8")

    warnings = security_warnings(str(broken))  # لا استثناء

    assert isinstance(warnings, list)


def test_check_is_read_only(monkeypatch, tmp_path):
    """الدالة لا تغيّر كلمة المرور: البصمة قبل وبعد متطابقة."""
    monkeypatch.setattr(config_module.settings, "SECRET_KEY", "a-real-random-secret")
    database = tmp_path / "fleet.db"
    _user_db(database, DEFAULT_ADMIN_PASSWORD)

    engine = create_engine(f"sqlite:///{database.as_posix()}")
    from sqlalchemy import text

    with engine.connect() as connection:
        before = connection.execute(
            text("SELECT hashed_password FROM users WHERE username='admin'")
        ).scalar()
    security_warnings(str(database))
    with engine.connect() as connection:
        after = connection.execute(
            text("SELECT hashed_password FROM users WHERE username='admin'")
        ).scalar()
    engine.dispose()

    assert before == after


def test_startup_logs_the_warnings(monkeypatch, caplog):
    """التحذير يصل إلى السجل عند الإقلاع (لا يبقى داخل دالة لا يستدعيها أحد)."""
    from fastapi.testclient import TestClient

    from web import main as web_main

    monkeypatch.setattr(config_module.settings, "SECRET_KEY", DEFAULT_SECRET_KEY)
    monkeypatch.setattr(web_main, "init_db", lambda: None)
    monkeypatch.setattr(web_main, "create_default_admin", lambda: None)
    monkeypatch.setattr(web_main, "_database_file", lambda: None)

    with caplog.at_level(logging.WARNING, logger="web.main"):
        with TestClient(web_main.create_app()):
            pass

    security_records = [r for r in caplog.records if "[security]" in r.message]
    assert security_records, "لم يُسجَّل أي تحذير أمني عند الإقلاع"
    assert any("SECRET_KEY" in r.message for r in security_records)


def test_startup_runs_even_when_everything_is_insecure(monkeypatch, caplog):
    """قرار صريح: التحذير لا يمنع الإقلاع (يبقى `admin/Admin@123` صالحاً)."""
    from fastapi.testclient import TestClient

    from web import main as web_main

    monkeypatch.setattr(config_module.settings, "SECRET_KEY", DEFAULT_SECRET_KEY)
    monkeypatch.setattr(web_main, "init_db", lambda: None)
    monkeypatch.setattr(web_main, "create_default_admin", lambda: None)
    monkeypatch.setattr(web_main, "_database_file", lambda: None)

    with caplog.at_level(logging.WARNING, logger="web.main"):
        with TestClient(web_main.create_app()) as client:
            response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
