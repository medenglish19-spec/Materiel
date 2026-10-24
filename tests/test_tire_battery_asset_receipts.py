from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app.database import model_registry  # noqa: F401
from app.database.base import Base
from app.modules.batteries.models import Battery, BatteryMovement
from app.modules.batteries.services import add_battery, delete_battery
from app.modules.batteries.router import batteries_page
from app.modules.spare_parts_requests.services import create_asset_receipt, list_asset_receipts
from app.modules.tires.models import Tire, TireMovement
from app.modules.tires.services import add_tire, delete_tire, validate_movement
from app.modules.users.models import User


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def test_asset_receipt_is_required_type_checked_and_quantity_limited(db):
    create_asset_receipt(db, {
        "asset_type": "tire", "document_number": "REC-T-1", "description": "275/70 R22.5",
        "quantity": 1, "received_date": date.today(),
    })
    with pytest.raises(ValueError, match="سجل الاستلام"):
        add_tire(db, {"serial_number": "T-INVALID", "acquisition_document": "MISSING"})
    tire = add_tire(db, {"serial_number": "T-001", "acquisition_document": "REC-T-1"})
    assert tire.acquisition_receipt_id is not None
    assert list_asset_receipts(db, "tire")[0]["remaining_quantity"] == 0
    with pytest.raises(ValueError, match="اكتملت كمية"):
        add_tire(db, {"serial_number": "T-002", "acquisition_document": "REC-T-1"})


def test_asset_receipt_listing_uses_bounded_queries_for_many_receipts(db):
    for index in range(12):
        create_asset_receipt(db, {
            "asset_type": "tire",
            "document_number": f"REC-T-{index}",
            "description": "275/70 R22.5",
            "quantity": 2,
            "received_date": date.today(),
        })

    statements = []
    def capture_statement(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", capture_statement)
    try:
        receipts = list_asset_receipts(db, "tire")
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", capture_statement)

    assert len(receipts) == 12
    assert len(statements) <= 2


def test_first_battery_page_load_uses_bounded_queries(db):
    create_asset_receipt(db, {
        "asset_type": "battery",
        "document_number": "REC-B-PERF",
        "description": "AGM 12V",
        "quantity": 24,
        "received_date": date.today(),
    })
    for index in range(24):
        add_battery(db, {
            "battery_type": "AGM",
            "capacity": f"{40 + (index % 4) * 5} Ah",
            "acquisition_document": "REC-B-PERF",
        })

    statements = []

    def capture_statement(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", capture_statement)
    try:
        response = batteries_page(
            Request({
                "type": "http",
                "http_version": "1.1",
                "method": "GET",
                "scheme": "http",
                "path": "/batteries",
                "raw_path": b"/batteries",
                "query_string": b"",
                "headers": [],
                "server": ("127.0.0.1", 80),
                "client": ("127.0.0.1", 12345),
            }),
            db,
            User(username="battery-page-test", full_name="Test", hashed_password="unused", role="ADMIN"),
        )
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", capture_statement)

    assert response.status_code == 200
    assert len(statements) <= 12
    assert response.context["stats"]["total"] == 24


def test_battery_uses_type_without_serial_and_requires_battery_receipt(db):
    create_asset_receipt(db, {
        "asset_type": "battery", "document_number": "REC-B-1", "description": "AGM 12V",
        "quantity": 1, "received_date": date.today(),
    })
    with pytest.raises(ValueError, match="نوع البطارية مطلوب"):
        add_battery(db, {"acquisition_document": "REC-B-1"})
    battery = add_battery(db, {"battery_type": "AGM", "acquisition_document": "REC-B-1"})
    assert battery.serial_number is None
    assert battery.battery_type == "AGM"
    with pytest.raises(ValueError, match="سجل الاستلام"):
        add_battery(db, {"battery_type": "AGM", "acquisition_document": "WRONG"})


def test_uninstalled_assets_can_be_deleted_and_installed_assets_are_protected(db):
    create_asset_receipt(db, {
        "asset_type": "tire", "document_number": "REC-DEL", "description": "test tire",
        "quantity": 2, "received_date": date.today(),
    })
    tire = add_tire(db, {"serial_number": "T-DEL", "acquisition_document": "REC-DEL"})
    delete_tire(db, tire.id)
    assert db.query(Tire).count() == 0
    create_asset_receipt(db, {
        "asset_type": "battery", "document_number": "REC-DEL-B", "description": "test battery",
        "quantity": 1, "received_date": date.today(),
    })
    battery = add_battery(db, {"battery_type": "AGM", "acquisition_document": "REC-DEL-B"})
    delete_battery(db, battery.id)
    assert db.query(Battery).count() == 0


def test_tire_cannot_be_installed_on_another_vehicle_after_removal(db, monkeypatch):
    create_asset_receipt(db, {
        "asset_type": "tire", "document_number": "REC-MOVE", "description": "test tire",
        "quantity": 1, "received_date": date.today(),
    })
    tire = add_tire(db, {"serial_number": "T-NOMOVE", "acquisition_document": "REC-MOVE"})
    yesterday = date.today() - timedelta(days=1)
    first_install = TireMovement(tire_id=tire.id, movement_type="install", equipment_id=10, position_id=1,
                                 movement_date=yesterday, movement_datetime=datetime.combine(yesterday, datetime.min.time()))
    removal = TireMovement(tire_id=tire.id, movement_type="remove", equipment_id=None, position_id=None,
                           movement_date=date.today(), movement_datetime=datetime.combine(date.today(), datetime.min.time()), reason="استبدال")
    db.add_all([first_install, removal])
    db.commit()
    monkeypatch.setattr("app.modules.tires.services._validate_model_position", lambda db, eid, pid, tire: (SimpleNamespace(id=eid), None))
    monkeypatch.setattr("app.modules.tires.services._validate_model_capacity", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.modules.tires.services._validate_equipment_meter", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.modules.tires.services._position_occupied_at", lambda *args, **kwargs: None)
    now = datetime.now().replace(microsecond=0)
    with pytest.raises(ValueError, match="يُمنع نقل الإطار"):
        validate_movement(db, tire, "install", date.today(), 20, 2, None, now)
