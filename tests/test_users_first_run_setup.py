import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.database import init_db as init_db_module
from app.database import model_registry  # noqa: F401
from app.database.base import Base
from app.database import session as database_session
from app.database.session import get_db
from app.modules.users import services
from app.modules.users.models import User
from app.modules.users.schemas import UserCreate
from web import main


@pytest.fixture
def first_run_app(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, autoflush=False)
    Base.metadata.create_all(engine)

    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setattr(settings, "DEV_DISABLE_AUTH", False)
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "create_default_admin", lambda: None)
    monkeypatch.setattr(main, "security_warnings", lambda *_args: [])
    monkeypatch.setattr(init_db_module, "_ADMIN_SETUP_REQUIRED", True)

    app = main.create_app()

    def override_db():
        with testing_session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(
            app,
            base_url="http://127.0.0.1:8000",
            client=("127.0.0.1", 50000),
        ) as client:
            yield client, testing_session
    finally:
        app.dependency_overrides.clear()
        init_db_module.complete_admin_setup()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_packaged_first_run_requires_a_private_admin_password(first_run_app):
    client, testing_session = first_run_app

    login = client.get("/login", follow_redirects=False)
    assert login.status_code == 303
    assert login.headers["location"] == "/setup"

    setup = client.get("/setup")
    assert setup.status_code == 200
    assert 'action="/setup"' in setup.text
    assert "لا توجد كلمة مرور افتراضية" in setup.text

    weak_password = client.post(
        "/setup",
        headers={"Origin": "http://127.0.0.1:8000"},
        data={"password": "short", "confirmation": "short"},
    )
    assert weak_password.status_code == 400
    assert "12 خانة" in weak_password.text
    assert init_db_module.admin_setup_required()

    password = "A-private-admin-password-2026!"
    created = client.post(
        "/setup",
        headers={"Origin": "http://127.0.0.1:8000"},
        data={"password": password, "confirmation": password},
        follow_redirects=False,
    )
    assert created.status_code == 303
    assert created.headers["location"] == "/dashboard"
    assert "fleet_session=" in created.headers.get("set-cookie", "")
    assert not init_db_module.admin_setup_required()

    with testing_session() as db:
        admin = db.query(User).filter(User.username == "admin").one()
        assert admin.role == "admin"
        assert admin.hashed_password != password
        assert services.authenticate_user(db, "admin", password) is not None
        assert services.authenticate_user(db, "admin", "Admin@123") is None

    setup_afterward = client.get("/setup", follow_redirects=False)
    assert setup_afterward.status_code == 303
    assert setup_afterward.headers["location"] == "/login"


def test_first_run_setup_is_not_available_from_a_remote_address(first_run_app):
    _client, _testing_session = first_run_app
    remote = TestClient(
        main.create_app(),
        client=("203.0.113.10", 50000),
    )

    response = remote.get("/setup")

    assert response.status_code == 404


def test_first_run_setup_rejects_cross_origin_password_claim(first_run_app):
    client, _testing_session = first_run_app

    response = client.post(
        "/setup",
        headers={"Origin": "http://attacker.example"},
        data={
            "password": "A-private-admin-password-2026!",
            "confirmation": "A-private-admin-password-2026!",
        },
    )

    assert response.status_code == 404
    assert init_db_module.admin_setup_required()


def test_first_run_setup_requires_origin_or_referer(first_run_app):
    client, _testing_session = first_run_app

    response = client.post(
        "/setup",
        data={
            "password": "A-private-admin-password-2026!",
            "confirmation": "A-private-admin-password-2026!",
        },
    )

    assert response.status_code == 404
    assert init_db_module.admin_setup_required()


def test_frozen_startup_does_not_create_the_published_default_admin(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, autoflush=False)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(database_session, "SessionLocal", testing_session)
    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setattr(init_db_module.sys, "frozen", True, raising=False)
    init_db_module.complete_admin_setup()
    try:
        init_db_module.create_default_admin()

        assert init_db_module.admin_setup_required()
        with testing_session() as db:
            assert db.query(User).count() == 0
    finally:
        init_db_module.complete_admin_setup()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_frozen_startup_forces_existing_default_admin_to_change_password(first_run_app, monkeypatch):
    client, testing_session = first_run_app
    with testing_session() as db:
        original = services.create_user(
            db,
            UserCreate(
                username="admin",
                full_name="مدير قائم",
                role="admin",
                password="Admin@123",
            ),
        )
        original_id = original.id

    monkeypatch.setattr(init_db_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(database_session, "SessionLocal", testing_session)
    init_db_module.create_default_admin()

    assert init_db_module.admin_setup_required()
    assert init_db_module.admin_setup_requires_password_change()
    setup = client.get("/setup")
    assert setup.status_code == 200
    assert "حساب المدير الحالي ما زال يستخدم كلمة المرور الأولية المنشورة" in setup.text

    new_password = "A-replaced-admin-password-2026!"
    response = client.post(
        "/setup",
        headers={"Origin": "http://127.0.0.1:8000"},
        data={"password": new_password, "confirmation": new_password},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/dashboard"
    assert not init_db_module.admin_setup_required()

    with testing_session() as db:
        admin = db.query(User).filter(User.username == "admin").one()
        assert admin.id == original_id
        assert admin.full_name == "مدير قائم"
        assert admin.role == "admin"
        assert admin.is_active is True
        assert services.authenticate_user(db, "admin", "Admin@123") is None
        assert services.authenticate_user(db, "admin", new_password) is not None


def test_frozen_runtime_ignores_environment_development_overrides(tmp_path, monkeypatch):
    from app.core import config

    monkeypatch.setattr(config.sys, "frozen", True, raising=False)
    monkeypatch.setattr(config, "packaged_data_directory", lambda: tmp_path / "MaterielData")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DEV_DISABLE_AUTH", "true")
    monkeypatch.setenv("SECRET_KEY", config.DEFAULT_SECRET_KEY)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///D:/must-not-be-used.db")
    monkeypatch.setenv("APP_HOST", "0.0.0.0")
    monkeypatch.setenv("APP_PORT", "not-a-port")
    monkeypatch.setenv("LOG_DIR", "D:/must-not-be-used/logs")

    assert config.application_environment() == "production"
    assert config.application_debug_enabled() is False
    assert config.dev_auth_disabled() is False
    generated = config.application_secret_key()
    assert generated != config.DEFAULT_SECRET_KEY
    assert len(generated) >= 32
    assert config.application_secret_key() == generated
    assert config.application_database_url().endswith("/MaterielData/fleet_assets.db")
    assert config.application_host() == "127.0.0.1"
    assert config.application_port() == 8000
    assert config.application_log_dir() == str(tmp_path / "MaterielData" / "logs")


def test_source_runtime_keeps_explicit_development_overrides(monkeypatch):
    from app.core import config

    monkeypatch.delattr(config.sys, "frozen", raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("DEV_DISABLE_AUTH", "true")
    assert config.application_environment() == "development"
    assert config.application_debug_enabled() is True
    assert config.dev_auth_disabled() is True
