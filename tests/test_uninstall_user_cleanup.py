"""Regression tests for uninstall-time removal of user authentication data.

These tests exercise the same SQLite work that ``Materiel.exe
--uninstall-cleanup`` performs during an Inno Setup uninstall.  They cover the
required A-E scenarios at the database/application level; the installer smoke
test covers the real Windows install/uninstall/update cycle.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import time
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.database import init_db as init_db_module
from app.database import model_registry  # noqa: F401
from app.database import session as database_session
from app.database.base import Base
from app.database.session import get_db
from app.database.uninstall_cleanup import (
    remove_user_accounts,
    run_uninstall_cleanup,
    update_is_in_progress,
)
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentModel, EquipmentType
from app.modules.faults_repairs.models import Fault
from app.modules.fuel.models import FuelRecord
from app.modules.maintenance.models import MaintenanceOperation, MaintenanceRecord
from app.modules.spare_parts_requests.models import SparePartRequest
from app.modules.users import services
from app.modules.users.models import User
from app.modules.users.schemas import UserCreate
from web import main


def _sqlite_engine(path):
    engine = create_engine(
        f"sqlite:///{path}",
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    return engine


def _seed_database(database_path):
    database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = _sqlite_engine(database_path)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False)
    with session_factory() as db:
        admin = services.create_user(
            db,
            UserCreate(
                username="admin-old",
                full_name="مدير قديم",
                password="OldAdmin-Password-2026!",
                role="admin",
            ),
        )
        operator = services.create_user(
            db,
            UserCreate(
                username="operator-old",
                full_name="مشغّل قديم",
                password="OldOperator-Password-2026!",
                role="operator",
            ),
        )
        equipment_type = EquipmentType(
            name="شاحنة اختبار",
            measurement_unit="km",
            is_frozen=False,
        )
        db.add(equipment_type)
        db.flush()
        equipment_model = EquipmentModel(
            name="طراز اختبار",
            equipment_type_id=equipment_type.id,
            mobility_type="mobile",
            requires_driver=False,
        )
        db.add(equipment_model)
        db.flush()
        equipment = Equipment(
            asset_code="QA-UNINSTALL-001",
            equipment_type_id=equipment_type.id,
            equipment_model_id=equipment_model.id,
            technical_condition="ready",
            operational_status="available",
            created_by_id=admin.id,
            updated_by_id=operator.id,
        )
        db.add(equipment)
        db.flush()
        operation = MaintenanceOperation(name="صيانة دورية", is_active=True)
        db.add(operation)
        db.flush()
        db.add(
            MaintenanceRecord(
                equipment_id=equipment.id,
                operation_id=operation.id,
                maintenance_date=date(2026, 1, 10),
                reported_date=date(2026, 1, 10),
                description="صيانة دورية",
                created_by_id=admin.id,
            )
        )
        db.add(
            FuelRecord(
                equipment_id=equipment.id,
                fueling_date=date(2026, 1, 11),
                sequence_number=1,
                quantity=40,
                fuel_type="ديزل",
                created_by_id=operator.id,
                updated_by_id=admin.id,
            )
        )
        db.add(
            Fault(
                equipment_id=equipment.id,
                reported_date=date(2026, 1, 12),
                description="عطل اختباري",
                created_by_id=operator.id,
            )
        )
        db.add(
            SparePartRequest(
                request_number="QA-REQ-001",
                request_date=date(2026, 1, 12),
                source_type="need",
                status="pending",
                requested_by_id=admin.id,
            )
        )
        db.commit()
        admin_id = admin.id
        operator_id = operator.id
    engine.dispose()
    return {"admin_id": admin_id, "operator_id": operator_id}


def _counts(database_path):
    with sqlite3.connect(database_path) as db:
        return {
            table: db.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in (
                "users",
                "equipment",
                "maintenance_records",
                "fuel_records",
                "faults",
                "spare_part_requests",
            )
        }


def _user_references(database_path):
    with sqlite3.connect(database_path) as db:
        tables = [
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        found = []
        for table in tables:
            if table == "users":
                continue
            for fk in db.execute(f'PRAGMA foreign_key_list("{table}")'):
                if fk[2] == "users":
                    non_null = db.execute(
                        f'SELECT COUNT(*) FROM "{table}" WHERE "{fk[3]}" IS NOT NULL'
                    ).fetchone()[0]
                    found.append((table, fk[3], non_null))
        return found


def _write_secret_key(data_directory):
    data_directory.mkdir(parents=True, exist_ok=True)
    key = data_directory / "secret.key"
    key.write_text("x" * 64, encoding="utf-8")
    return key


def test_uninstall_removes_accounts_but_preserves_business_data(tmp_path):
    """Scenario A/B/E: operational history survives; users and sessions do not."""
    data_directory = tmp_path / "data"
    database_path = data_directory / "fleet_assets.db"
    _seed_database(database_path)
    secret_key = _write_secret_key(data_directory)
    before = _counts(database_path)
    assert before["users"] == 2
    assert before["equipment"] == 1
    assert before["maintenance_records"] == 1
    assert before["fuel_records"] == 1
    assert before["faults"] == 1
    assert before["spare_part_requests"] == 1

    result = remove_user_accounts(database_path, data_directory=data_directory)

    after = _counts(database_path)
    assert result["status"] == "ok"
    assert result["users_deleted"] == 2
    assert result["integrity_check"] == "ok"
    assert result["foreign_key_violations"] == 0
    assert result["secret_key_removed"] is True
    assert not secret_key.exists()
    assert after["users"] == 0
    for table in (
        "equipment",
        "maintenance_records",
        "fuel_records",
        "faults",
        "spare_part_requests",
    ):
        assert after[table] == before[table], table
    assert all(count == 0 for _table, _column, count in _user_references(database_path))

    with sqlite3.connect(database_path) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0


def test_reinstall_shows_first_run_setup_and_rejects_old_credentials(tmp_path, monkeypatch):
    """Scenario C: a reinstall starts at first-run setup and keeps business data."""
    data_directory = tmp_path / "data"
    database_path = data_directory / "fleet_assets.db"
    _seed_database(database_path)
    remove_user_accounts(database_path, data_directory=data_directory)

    engine = _sqlite_engine(database_path)
    testing_session = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setenv("MATERIEL_DATA_DIR", str(data_directory))
    monkeypatch.setattr(settings, "ENV", "production")
    monkeypatch.setattr(settings, "DEV_DISABLE_AUTH", False)
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "create_default_admin", lambda: None)
    monkeypatch.setattr(main, "security_warnings", lambda *_args: [])
    monkeypatch.setattr(init_db_module.sys, "frozen", True, raising=False)
    monkeypatch.setattr(database_session, "SessionLocal", testing_session)
    init_db_module.complete_admin_setup()

    try:
        init_db_module.create_default_admin()
        assert init_db_module.admin_setup_required()

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
                login_page = client.get("/login", follow_redirects=False)
                assert login_page.status_code == 303
                assert login_page.headers["location"] == "/setup"

                setup_page = client.get("/setup")
                assert setup_page.status_code == 200
                assert 'action="/setup"' in setup_page.text

                new_username = "admin-new"
                new_password = "NewAdmin-Password-2026!"
                created = client.post(
                    "/setup",
                    headers={"Origin": "http://127.0.0.1:8000"},
                    data={
                        "username": new_username,
                        "password": new_password,
                        "confirmation": new_password,
                    },
                    follow_redirects=False,
                )
                assert created.status_code == 303
                assert created.headers["location"] == "/dashboard"
                assert not init_db_module.admin_setup_required()

                client.get("/logout")
                old_login = client.post(
                    "/login",
                    data={
                        "username": "admin-old",
                        "password": "OldAdmin-Password-2026!",
                    },
                    follow_redirects=False,
                )
                assert old_login.status_code == 401

                new_login = client.post(
                    "/login",
                    data={"username": new_username, "password": new_password},
                    follow_redirects=False,
                )
                assert new_login.status_code == 302
                assert new_login.headers["location"] == "/dashboard"

                dashboard = client.get("/dashboard")
                assert dashboard.status_code == 200
        finally:
            app.dependency_overrides.clear()

        with testing_session() as db:
            assert db.query(User).count() == 1
            assert db.query(User).filter(User.username == new_username).one().role == "admin"
            assert db.query(Equipment).count() == 1
            assert db.query(MaintenanceRecord).count() == 1
            assert db.query(FuelRecord).count() == 1
            assert db.query(Fault).count() == 1
            assert db.query(SparePartRequest).count() == 1
    finally:
        init_db_module.complete_admin_setup()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_update_marker_skips_cleanup_and_preserves_accounts(tmp_path, monkeypatch):
    """Scenario D: an installer update must not delete user accounts."""
    data_directory = tmp_path / "data"
    database_path = data_directory / "fleet_assets.db"
    _seed_database(database_path)
    _write_secret_key(data_directory)

    marker = tmp_path / "update-in-progress"
    marker.write_text(f"{os.getpid()}|20260101-120000", encoding="utf-8")
    monkeypatch.setenv("MATERIEL_DATA_DIR", str(data_directory))
    monkeypatch.setenv("MATERIEL_UPDATE_MARKER", str(marker))
    monkeypatch.setenv("MATERIEL_ALLOW_UNINSTALL_CLEANUP", "1")
    assert update_is_in_progress() is True

    assert run_uninstall_cleanup() == 0

    assert _counts(database_path)["users"] == 2
    assert (data_directory / "secret.key").exists()
    assert marker.exists()


def test_stale_update_marker_does_not_block_real_uninstall(tmp_path, monkeypatch):
    data_directory = tmp_path / "data"
    database_path = data_directory / "fleet_assets.db"
    _seed_database(database_path)
    marker = tmp_path / "update-in-progress"
    marker.write_text(f"{2**31 - 1}|20260101-120000", encoding="utf-8")
    old = time.time() - (7 * 60 * 60)
    os.utime(marker, (old, old))
    monkeypatch.setenv("MATERIEL_DATA_DIR", str(data_directory))
    monkeypatch.setenv("MATERIEL_UPDATE_MARKER", str(marker))
    monkeypatch.setenv("MATERIEL_ALLOW_UNINSTALL_CLEANUP", "1")

    assert update_is_in_progress() is False
    assert not marker.exists()
    assert run_uninstall_cleanup() == 0
    assert _counts(database_path)["users"] == 0


def test_missing_database_is_reported_without_creating_one(tmp_path):
    data_directory = tmp_path / "data"
    data_directory.mkdir()
    secret_key = _write_secret_key(data_directory)
    database_path = data_directory / "fleet_assets.db"

    result = remove_user_accounts(database_path, data_directory=data_directory)

    assert result["status"] == "database_missing"
    assert not database_path.exists()
    assert result["secret_key_removed"] is True
    assert not secret_key.exists()


def test_corrupt_database_is_not_modified(tmp_path, monkeypatch):
    data_directory = tmp_path / "data"
    data_directory.mkdir()
    database_path = data_directory / "fleet_assets.db"
    original = b"this is not a sqlite database"
    database_path.write_bytes(original)
    monkeypatch.setenv("MATERIEL_DATA_DIR", str(data_directory))
    monkeypatch.delenv("MATERIEL_UPDATE_MARKER", raising=False)
    monkeypatch.setenv("MATERIEL_ALLOW_UNINSTALL_CLEANUP", "1")

    with pytest.raises(sqlite3.DatabaseError):
        remove_user_accounts(database_path, data_directory=data_directory)

    assert database_path.read_bytes() == original
    assert run_uninstall_cleanup() == 1
    log_path = data_directory / "uninstall-auth-cleanup.log"
    assert log_path.exists()
    assert '"status": "failed"' in log_path.read_text(encoding="utf-8")


def test_cleanup_refuses_to_run_outside_uninstaller_without_override(tmp_path, monkeypatch):
    data_directory = tmp_path / "data"
    database_path = data_directory / "fleet_assets.db"
    _seed_database(database_path)
    monkeypatch.setenv("MATERIEL_DATA_DIR", str(data_directory))
    monkeypatch.delenv("MATERIEL_ALLOW_UNINSTALL_CLEANUP", raising=False)
    monkeypatch.delenv("MATERIEL_UPDATE_MARKER", raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)

    assert run_uninstall_cleanup() == 2
    assert _counts(database_path)["users"] == 2
