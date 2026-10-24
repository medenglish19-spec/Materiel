from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.requests import Request

from app.database import model_registry  # noqa: F401
from app.database.base import Base
from app.core.dependencies import get_current_user
from app.database.session import get_db
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentModel, EquipmentType
from app.modules.missions import services
from app.modules.missions.models import Driver, Mission
from app.modules.missions.router import (
    drivers_page,
    driver_history_page,
    edit_driver_page,
    missions_page,
    update_center_column_label,
)
from app.modules.users.models import User
from web import main


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _equipment(db, *, requires_driver: bool, registration_number: str):
    equipment_type = EquipmentType(
        name=f"نوع {registration_number}",
        measurement_unit="km",
    )
    db.add(equipment_type)
    db.flush()
    model = EquipmentModel(
        name=f"طراز {registration_number}",
        equipment_type_id=equipment_type.id,
        requires_driver=requires_driver,
    )
    db.add(model)
    db.flush()
    equipment = Equipment(
        asset_code=f"ASSET-{registration_number}",
        registration_number=registration_number,
        equipment_type_id=equipment_type.id,
        equipment_model_id=model.id,
        operational_status="available",
    )
    db.add(equipment)
    db.commit()
    return equipment


def _driver_data(employee_number: str, equipment_id: int | None = None):
    return {
        "employee_number": employee_number,
        "first_name": "أحمد",
        "last_name": "السائق",
        "center": "المركز الأول",
        "license_class": "C",
        "assigned_equipment_id": equipment_id,
        "notes": "اختبار",
    }


def _request(path: str):
    raw_path = path.encode("utf-8")
    return Request({
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": raw_path,
        "query_string": b"",
        "headers": [],
        "server": ("127.0.0.1", 80),
        "client": ("127.0.0.1", 12345),
    })


def test_multiple_drivers_can_share_only_equipment_that_requires_a_driver(db):
    required = _equipment(db, requires_driver=True, registration_number="DRV-1")
    optional = _equipment(db, requires_driver=False, registration_number="DRV-2")

    first = services.create_driver(db, _driver_data("EMP-1", required.id))
    second = services.create_driver(db, _driver_data("EMP-2", required.id))

    assert first.assigned_equipment_id == second.assigned_equipment_id == required.id
    with pytest.raises(ValueError, match="يتطلب سائقًا"):
        services.create_driver(db, _driver_data("EMP-3", optional.id))
    with pytest.raises(ValueError, match="مستخدم مسبقًا"):
        services.create_driver(db, _driver_data("EMP-1"))


def test_driver_can_be_edited_and_deactivated_without_deleting_history(db):
    driver = services.create_driver(db, _driver_data("EMP-EDIT"))
    updated = services.update_driver(
        db,
        driver.id,
        {
            **_driver_data("EMP-EDIT-2"),
            "center": "مركز جديد",
            "notes": "ملاحظة محدثة",
        },
    )
    services.set_driver_active(db, driver.id, False)

    stored = db.query(Driver).filter(Driver.id == driver.id).one()
    assert updated.employee_number == "EMP-EDIT-2"
    assert stored.center == "مركز جديد"
    assert stored.notes == "ملاحظة محدثة"
    assert stored.is_active is False
    assert services.get_driver(db, driver.id) is not None


def test_license_dates_are_validated_and_expiry_alerts_include_day_30(db):
    today = date.today()
    with pytest.raises(ValueError, match="المستقبل"):
        services.create_driver(
            db,
            {
                **_driver_data("EMP-FUTURE"),
                "license_issue_date": today + timedelta(days=1),
            },
        )
    with pytest.raises(ValueError, match="يسبق"):
        services.create_driver(
            db,
            {
                **_driver_data("EMP-ORDER"),
                "license_issue_date": today,
                "license_expiry_date": today - timedelta(days=1),
            },
        )

    expired = services.create_driver(
        db,
        {**_driver_data("EMP-EXPIRED"), "license_expiry_date": today - timedelta(days=1)},
    )
    expiring = services.create_driver(
        db,
        {
            **_driver_data("EMP-EXPIRING"),
            "license_issue_date": today - timedelta(days=365),
            "license_expiry_date": today + timedelta(days=30),
        },
    )
    later = services.create_driver(
        db,
        {**_driver_data("EMP-LATER"), "license_expiry_date": today + timedelta(days=31)},
    )
    services.set_driver_active(db, later.id, False)

    alerts = services.license_expiry_alerts(services.list_drivers(db), today=today)
    assert [driver.id for driver in alerts["expired"]] == [expired.id]
    assert [driver.id for driver in alerts["expiring_soon"]] == [expiring.id]
    admin = User(username="admin", full_name="مدير النظام", hashed_password="unused", role="admin")
    driver_page = drivers_page(_request("/missions/drivers"), db, admin)
    assert driver_page.status_code == 200
    assert "تنبيهات صلاحية الرخص" not in driver_page.body.decode("utf-8")
    mission_page = missions_page(_request("/missions"), db, admin)
    assert mission_page.status_code == 200
    mission_html = mission_page.body.decode("utf-8")
    assert "تنتهي خلال 30 يومًا" in mission_html
    assert "منتهية</span>" in mission_html
    assert expired.first_name in mission_html and expiring.last_name in mission_html
    edit = edit_driver_page(
        expiring.id,
        _request(f"/missions/drivers/{expiring.id}/edit"),
        db,
        admin,
    )
    issue_date = (today - timedelta(days=365)).isoformat()
    expiry_date = (today + timedelta(days=30)).isoformat()
    assert f'value="{issue_date}"' in edit.body.decode("utf-8")
    assert f'value="{expiry_date}"' in edit.body.decode("utf-8")


def test_registered_driver_must_be_active_and_assigned_to_mission_equipment(db):
    assigned = _equipment(db, requires_driver=True, registration_number="DRV-MISSION")
    other = _equipment(db, requires_driver=True, registration_number="DRV-OTHER")
    driver = services.create_driver(db, _driver_data("EMP-MISSION", assigned.id))
    mission_data = {
        "equipment_id": assigned.id,
        "driver_id": driver.id,
        "start_date": date.today(),
    }

    with pytest.raises(ValueError, match="غير معيّن"):
        services.add_mission(db, {**mission_data, "equipment_id": other.id})

    services.set_driver_active(db, driver.id, False)
    with pytest.raises(ValueError, match="غير نشط"):
        services.add_mission(db, mission_data)


def test_driver_mission_history_uses_relationship_and_unambiguous_legacy_names(db):
    equipment = _equipment(db, requires_driver=True, registration_number="DRV-HISTORY")
    driver = services.create_driver(db, _driver_data("EMP-HISTORY", equipment.id))
    today = date.today()
    linked = services.add_mission(
        db,
        {
            "equipment_id": equipment.id,
            "driver_id": driver.id,
            "start_date": today - timedelta(days=1),
            "end_date": today,
            "departure_meter": Decimal("100"),
            "return_meter": Decimal("110"),
        },
    )
    legacy = Mission(
        equipment_id=equipment.id,
        driver_name=f"{driver.first_name} {driver.last_name}",
        start_date=today - timedelta(days=2),
    )
    db.add_all([linked, legacy])
    db.commit()

    missions, legacy_count = services.list_driver_missions(db, driver)
    assert {mission.id for mission in missions} == {linked.id, legacy.id}
    assert legacy_count == 1
    linked_mission = next(mission for mission in missions if mission.id == linked.id)
    assert linked_mission.departure_meter == Decimal("100")
    assert linked_mission.return_meter == Decimal("110")

    duplicate_name = services.create_driver(
        db,
        {
            **_driver_data("EMP-DUPLICATE", equipment.id),
            "first_name": driver.first_name,
            "last_name": driver.last_name,
        },
    )
    missions, legacy_count = services.list_driver_missions(db, driver)
    assert [mission.id for mission in missions] == [linked.id]
    assert legacy_count == 0
    assert duplicate_name.id != driver.id

    statement_count = 0

    def count_statement(*_args):
        nonlocal statement_count
        statement_count += 1

    event.listen(db.get_bind(), "before_cursor_execute", count_statement)
    response = driver_history_page(
        driver.id,
        _request(f"/missions/drivers/{driver.id}"),
        db,
        User(username="viewer", full_name="قارئ", hashed_password="unused", role="viewer"),
    )
    event.remove(db.get_bind(), "before_cursor_execute", count_statement)
    assert response.status_code == 200
    assert "سجل مهمات" in response.body.decode("utf-8")
    assert statement_count <= 5
    assert "100.0" in response.body.decode("utf-8")
    assert "110.0" in response.body.decode("utf-8")


def test_center_header_label_is_shared_and_does_not_change_center_values(db):
    equipment = _equipment(db, requires_driver=True, registration_number="DRV-LABEL")
    unassigned_equipment = _equipment(db, requires_driver=True, registration_number="DRV-UNASSIGNED")
    driver = services.create_driver(db, _driver_data("EMP-LABEL", equipment.id))
    admin = User(
        username="admin",
        full_name="مدير النظام",
        hashed_password="unused",
        role="admin",
    )
    update_response = update_center_column_label("الوحدة", db, admin)
    response = drivers_page(
        _request("/missions/drivers"),
        db,
        admin,
    )
    edit_response = edit_driver_page(
        driver.id,
        _request(f"/missions/drivers/{driver.id}/edit"),
        db,
        admin,
    )

    assert response.status_code == 200
    assert update_response.status_code == 303
    assert "الوحدة" in response.body.decode("utf-8")
    assert "DRV-LABEL" in response.body.decode("utf-8")
    assert f"({1})</b>" in response.body.decode("utf-8")
    assert f'data-add-driver-for="{unassigned_equipment.id}"' in response.body.decode("utf-8")
    assert "DRV-LABEL" in edit_response.body.decode("utf-8")
    assert db.query(Driver).filter(Driver.id == driver.id).one().center == "المركز الأول"
    assert services.get_driver_system_setting(db).center_column_label == "الوحدة"


def test_only_admin_can_change_the_center_column_label(db):
    viewer = User(
        username="viewer",
        full_name="قارئ",
        hashed_password="unused",
        role="viewer",
    )

    with pytest.raises(HTTPException) as error:
        update_center_column_label("الوحدة", db, viewer)

    assert error.value.status_code == 403
    assert services.get_driver_system_setting(db).center_column_label == "المركز"


def test_driver_header_sequence_is_rendered_and_label_editor_is_admin_only(db):
    services.create_driver(db, _driver_data("EMP-VIEW"))
    services.create_driver(
        db,
        {
            **_driver_data("EMP-VIEW-2"),
            "first_name": "اسم أسبق ترتيبًا",
            "last_name": "اختبار",
        },
    )
    response = drivers_page(
        _request("/missions/drivers"),
        db,
        User(username="viewer", full_name="قارئ", hashed_password="unused", role="viewer"),
    )
    html = response.body.decode("utf-8")

    assert "<th>الرقم</th>" in html
    assert "رقم الترتيب" not in html
    assert "EMP-VIEW" not in html
    assert ">1</td>" in html
    assert ">2</td>" in html
    assert "تغيير تسمية عمود المركز" not in html


def test_driver_page_and_admin_label_setting_over_http(db, monkeypatch):
    equipment = _equipment(db, requires_driver=True, registration_number="DRV-HTTP")
    admin = User(
        username="admin",
        full_name="مدير النظام",
        hashed_password="unused",
        role="admin",
    )
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "create_default_admin", lambda: None)
    app = main.create_app()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: admin

    with TestClient(app) as client:
        created = client.post(
            "/missions/drivers",
            data={
                "first_name": "سائق",
                "last_name": "اختبار",
                "license_class": "C",
                "center": "مركز أ",
                "assigned_equipment_id": str(equipment.id),
            },
            follow_redirects=False,
        )
        assert created.status_code == 303

        mission_created = client.post(
            "/missions",
            data={
                "equipment_id": str(equipment.id),
                "driver_id": "1",
                "start_date": date.today().isoformat(),
                "purpose": "اختبار سجل السائق",
                "mission_document": "MISSION-HTTP-1",
                "destination": "مركز الاختبار",
                "notes": "ملاحظة المهمة",
            },
            follow_redirects=False,
        )
        assert mission_created.status_code == 303
        mission = db.query(Mission).one()
        assert mission.driver_id == 1
        assert mission.driver_name == "سائق اختبار"
        mission_page = client.get("/missions")
        assert "DRV-HTTP" in mission_page.text
        assert "مركز أ - سائق اختبار" in mission_page.text
        records_page = client.get("/missions/records")
        assert records_page.status_code == 200
        assert "<th>العتاد</th><th>رقم التسجيل</th><th>السائق</th>" in records_page.text
        assert "<td>DRV-HTTP</td>" in records_page.text
        assert "مركز الاختبار" in records_page.text
        assert "ملاحظة المهمة" in records_page.text
        history = client.get("/missions/drivers/1")
        assert history.status_code == 200
        assert "اختبار سجل السائق" in history.text
        assert "MISSION-HTTP-1" in history.text

        page = client.get("/missions/drivers")
        assert page.status_code == 200
        assert "DRV-HTTP" in page.text
        assert "سائق" in page.text

        renamed = client.post(
            "/missions/drivers/settings/center-column-label",
            data={"center_column_label": "الفرقة"},
            follow_redirects=False,
        )
        assert renamed.status_code == 303
        assert "الفرقة" in client.get("/missions/drivers").text
