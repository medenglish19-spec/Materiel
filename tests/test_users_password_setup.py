import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.dependencies import get_current_user
from app.database import model_registry  # noqa: F401
from app.database.base import Base
from app.database.session import get_db
from app.modules.users import services
from app.modules.users.models import User
from app.modules.users.schemas import UserCreate
from web import main


@pytest.fixture
def users_app(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, autoflush=False)
    Base.metadata.create_all(engine)
    with testing_session() as db:
        admin = services.create_user(
            db,
            UserCreate(
                username="admin",
                full_name="مدير النظام",
                role="admin",
                password="Admin@123",
            ),
        )
        admin_id = admin.id

    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "create_default_admin", lambda: None)
    app = main.create_app()

    def override_db():
        with testing_session() as db:
            yield db

    def override_current_user(db: Session = Depends(get_db)):
        return db.query(User).filter(User.id == admin_id).one()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_current_user
    try:
        with TestClient(app) as client:
            yield client, testing_session, admin_id
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_admin_can_set_and_use_a_private_password_after_install(users_app):
    client, testing_session, admin_id = users_app
    page = client.get("/users")
    assert page.status_code == 200
    assert "إعداد كلمة مرور مدير النظام" in page.text
    assert 'action="/users/password"' in page.text

    changed = client.post(
        "/users/password",
        data={
            "current_password": "Admin@123",
            "new_password": "PrivateAdmin@2026",
            "confirmation": "PrivateAdmin@2026",
        },
        follow_redirects=False,
    )
    assert changed.status_code == 303
    assert changed.headers["location"] == "/login?password_changed=1"
    assert "max-age=0" in changed.headers.get("set-cookie", "").lower()

    with testing_session() as db:
        stored = db.query(User).filter(User.id == admin_id).one()
        assert services.authenticate_user(db, "admin", "PrivateAdmin@2026") is not None
        assert services.authenticate_user(db, "admin", "Admin@123") is None
        assert stored.hashed_password != "PrivateAdmin@2026"

    login_page = client.get(changed.headers["location"])
    assert login_page.status_code == 200
    assert "تم تحديث كلمة المرور" in login_page.text
    login = client.post(
        "/login",
        data={"username": "admin", "password": "PrivateAdmin@2026"},
        follow_redirects=False,
    )
    assert login.status_code == 302
    assert login.headers["location"] == "/dashboard"


@pytest.mark.parametrize(
    ("current_password", "new_password", "confirmation", "expected"),
    [
        ("wrong", "PrivateAdmin@2026", "PrivateAdmin@2026", "الحالية غير صحيحة"),
        ("Admin@123", "PrivateAdmin@2026", "DifferentPassword@2026", "غير مطابق"),
        ("Admin@123", "short", "short", "6 خانات"),
    ],
)
def test_admin_password_change_rejects_invalid_values(
    users_app, current_password, new_password, confirmation, expected
):
    client, _, _ = users_app
    response = client.post(
        "/users/password",
        data={
            "current_password": current_password,
            "new_password": new_password,
            "confirmation": confirmation,
        },
    )
    assert response.status_code == 400
    assert expected in response.text
