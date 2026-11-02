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
from app.modules.batteries.router import batteries_page
from app.modules.batteries.services import add_battery, delete_battery
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentType
from app.modules.faults_repairs.models import Fault
from app.modules.spare_parts_requests.schemas import SparePartRequestCreate, SparePartRequestItemCreate
from app.modules.spare_parts_requests.services import available_asset_request_items, create_request, received_register
from app.modules.spare_parts_requests.router import router as spare_parts_requests_router
from app.modules.tires.models import Tire, TireMovement
from app.modules.tires.services import add_tire, delete_tire, validate_movement
from app.modules.users.models import User


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    user = User(username="asset-request-test", full_name="Test", hashed_password="unused", role="ADMIN")
    equipment_type = EquipmentType(name="نوع أصل مستلم", measurement_unit="km")
    session.add_all([user, equipment_type])
    session.flush()
    equipment = Equipment(
        asset_code="ASSET-REQUEST-1",
        equipment_type_id=equipment_type.id,
        operational_status="available",
    )
    session.add(equipment)
    session.commit()
    session.info["equipment_id"] = equipment.id
    session.info["user_id"] = user.id
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


def _received_request_item(db, asset_type: str, number: str, quantity: int = 1):
    request_date = date.today() - timedelta(days=1)
    fault = Fault(
        equipment_id=db.info["equipment_id"],
        reported_date=request_date,
        description=f"طلب {asset_type} {number}",
    )
    db.add(fault)
    db.flush()
    request = create_request(
        db,
        SparePartRequestCreate(
            request_number=number,
            request_date=request_date,
            received_date=date.today(),
            recipient="مستودع الاختبار",
            supplier_institution="المورد الاختباري",
            source_type="fault",
            source_id=fault.id,
            items=[SparePartRequestItemCreate(
                asset_type=asset_type,
                part_name=f"صنف {asset_type}",
                requested_quantity=quantity,
                received_quantity=quantity,
            )],
        ),
        db.info["user_id"],
    )
    return request, request.items[0]


def test_dedicated_asset_receipt_screen_and_api_are_removed():
    received_template = open("app/modules/spare_parts_requests/templates/received.html", encoding="utf-8").read()
    tire_template = open("app/modules/tires/templates/tires.html", encoding="utf-8").read()
    battery_template = open("app/modules/batteries/templates/batteries.html", encoding="utf-8").read()

    assert "استلام الإطارات والبطاريات" not in received_template
    assert "/asset-receipts" not in received_template
    assert not any(route.path.endswith("/asset-receipts") for route in spare_parts_requests_router.routes)
    assert 'name="acquisition_request_item_id"' in tire_template
    assert 'name="acquisition_request_item_id"' in battery_template
    assert "tire-receipts" not in tire_template
    assert "battery-receipts" not in battery_template


def test_tires_are_registered_from_approved_received_requests_and_limited(db):
    request, item = _received_request_item(db, "tire", "REQ-T-1", quantity=1)
    received = received_register(db)
    assert received[0]["asset_type"] == "tire"
    assert received[0]["request_number"] == request.request_number

    with pytest.raises(ValueError, match="اختر بند إطار مستلمًا"):
        add_tire(db, {"serial_number": "T-INVALID", "acquisition_request_item_id": 99999})
    tire = add_tire(db, {"serial_number": "T-001", "acquisition_request_item_id": item.id})
    assert tire.acquisition_request_item_id == item.id
    assert tire.acquisition_document == request.request_number
    assert tire.receipt_date == request.received_date
    assert available_asset_request_items(db, "tire") == []
    with pytest.raises(ValueError, match="اكتملت كمية الإطارات"):
        add_tire(db, {"serial_number": "T-002", "acquisition_request_item_id": item.id})


def test_available_received_asset_items_use_bounded_queries(db):
    for index in range(12):
        _received_request_item(db, "tire", f"REQ-T-{index}", quantity=2)

    statements = []

    def capture_statement(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    event.listen(db.get_bind(), "before_cursor_execute", capture_statement)
    try:
        receipts = available_asset_request_items(db, "tire")
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", capture_statement)

    assert len(receipts) == 12
    assert all(row["remaining_quantity"] == 2 for row in receipts)
    assert len(statements) <= 4


def test_first_battery_page_load_uses_bounded_queries(db):
    _request, item = _received_request_item(db, "battery", "REQ-B-PERF", quantity=24)
    for index in range(24):
        add_battery(db, {
            "battery_type": "AGM",
            "capacity": f"{40 + (index % 4) * 5} Ah",
            "acquisition_request_item_id": item.id,
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
            db.get(User, db.info["user_id"]),
        )
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", capture_statement)

    assert response.status_code == 200
    assert len(statements) <= 12
    assert response.context["stats"]["total"] == 24
    assert response.context["battery_request_items"] == []


def test_battery_requires_type_and_received_battery_request_item(db):
    _request, item = _received_request_item(db, "battery", "REQ-B-1", quantity=1)
    with pytest.raises(ValueError, match="نوع البطارية مطلوب"):
        add_battery(db, {"acquisition_request_item_id": item.id})
    battery = add_battery(db, {"battery_type": "AGM", "acquisition_request_item_id": item.id})
    assert battery.serial_number is None
    assert battery.battery_type == "AGM"
    assert battery.acquisition_document == "REQ-B-1"
    with pytest.raises(ValueError, match="اختر بند بطارية مستلمًا"):
        add_battery(db, {"battery_type": "AGM", "acquisition_request_item_id": 99999})


def test_uninstalled_assets_can_be_deleted(db):
    _request, tire_item = _received_request_item(db, "tire", "REQ-DEL-T", quantity=1)
    tire = add_tire(db, {"serial_number": "T-DEL", "acquisition_request_item_id": tire_item.id})
    delete_tire(db, tire.id)
    assert db.query(Tire).count() == 0

    _request, battery_item = _received_request_item(db, "battery", "REQ-DEL-B", quantity=1)
    battery = add_battery(db, {"battery_type": "AGM", "acquisition_request_item_id": battery_item.id})
    delete_battery(db, battery.id)
    assert db.query(Battery).count() == 0


def test_tire_cannot_be_installed_on_another_vehicle_after_removal(db, monkeypatch):
    _request, item = _received_request_item(db, "tire", "REQ-MOVE-T", quantity=1)
    tire = add_tire(db, {"serial_number": "T-NOMOVE", "acquisition_request_item_id": item.id})
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
