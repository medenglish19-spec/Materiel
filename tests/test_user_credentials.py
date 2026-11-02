import importlib
import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password, pwd_context, verify_password
from app.database import model_registry  # noqa: F401
from app.database.base import Base
from app.modules.users.models import User


def test_new_user_schema_accepts_long_names_and_rejects_empty_names(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'users.db').as_posix()}")
    Base.metadata.create_all(engine)

    with Session(engine) as db:
        db.add(
            User(
                username="مستخدم" * 30,
                full_name="مستخدم اختبار",
                hashed_password=hash_password("x"),
                role="viewer",
            )
        )
        db.commit()
        assert db.query(User).count() == 1

        db.add(
            User(
                username="",
                full_name="مستخدم فارغ",
                hashed_password=hash_password("x"),
                role="viewer",
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()

    engine.dispose()


def test_existing_user_schema_migration_rejects_empty_names_and_accepts_arabic(tmp_path):
    database = tmp_path / "legacy-users.db"
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                username VARCHAR(50) NOT NULL UNIQUE,
                full_name VARCHAR(150) NOT NULL,
                hashed_password VARCHAR(255) NOT NULL,
                role VARCHAR(30) NOT NULL,
                is_active BOOLEAN NOT NULL
            )
            """
        )
        connection.exec_driver_sql(
            "INSERT INTO users VALUES (1, 'legacy', 'Legacy', 'hash', 'admin', 1)"
        )
        migration = importlib.import_module(
            "migrations.versions.20261102_user_credentials"
        )
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()

        with pytest.raises(IntegrityError, match="username must not be empty"):
            connection.exec_driver_sql(
                "INSERT INTO users VALUES (2, '', 'Empty', 'hash', 'viewer', 1)"
            )
        with pytest.raises(IntegrityError, match="username must not be empty"):
            connection.exec_driver_sql("UPDATE users SET username = '' WHERE id = 1")
        connection.exec_driver_sql(
            "INSERT INTO users VALUES (3, 'مدير-اختبار', 'Arabic', 'hash', 'admin', 1)"
        )
        connection.exec_driver_sql(
            "INSERT INTO users VALUES (4, ?, 'Long', 'hash', 'viewer', 1)",
            ("اسم" * 100,),
        )
    engine.dispose()


def test_password_hash_supports_long_values_and_preserves_legacy_bcrypt():
    prefix = "أ" * 36
    first = prefix + "SharedSuffix!"
    second = prefix + "SharedSuffix?"
    first_hash = hash_password(first)

    assert len(first.encode("utf-8")) > 72
    assert pwd_context.identify(first_hash) == "bcrypt_sha256"
    assert verify_password(first, first_hash)
    assert not verify_password(second, first_hash)

    legacy_hash = pwd_context.hash("legacy-password", scheme="bcrypt")
    assert verify_password("legacy-password", legacy_hash)
    assert not verify_password(prefix + "legacy-password", legacy_hash)


def test_password_hash_rejects_empty_passwords():
    with pytest.raises(ValueError, match="كلمة المرور مطلوبة"):
        hash_password("")
