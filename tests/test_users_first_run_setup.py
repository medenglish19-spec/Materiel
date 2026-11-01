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
