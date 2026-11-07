from datetime import date, datetime
from urllib.parse import unquote

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.database.base import Base
from app.core.config import settings
from app.core.dependencies import get_current_user
from app.database.session import get_db
from app.modules.equipment.models import Equipment
from app.modules.equipment.schemas import EquipmentCreate, EquipmentUpdate
from app.modules.equipment_types.models import EquipmentType, EquipmentModel
from app.modules.equipment import services
from app.modules.meter_readings import services as meter_services
from app.modules.meter_readings.models import MeterReading
from app.modules.meter_readings.audit import MeterReadingChange
from app.modules.users.models import User
from web import main


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Session = sessionmaker(bind=engine)


def test_equipment_edit_updates_fields_and_rejects_duplicate_identifiers():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = Session()
    try:
        type_a = EquipmentType(name="نوع اختبار التعديل", measurement_unit="km")
        type_b = EquipmentType(name="نوع آخر للتعديل", measurement_unit="hours")
        db.add_all([type_a, type_b])
        db.flush()
        model_a = EquipmentModel(name="طراز اختبار التعديل", equipment_type_id=type_a.id)
        model_b = EquipmentModel(name="طراز آخر للتعديل", equipment_type_id=type_b.id)
        db.add_all([model_a, model_b])
        db.flush()

        first = Equipment(
            asset_code="EDIT-1",
            registration_number="EDIT-REG-1",
            vin="EDIT-VIN-1",
            equipment_type_id=type_a.id,
            equipment_model_id=model_a.id,
        )
        second = Equipment(
            asset_code="EDIT-2",
            registration_number="EDIT-REG-2",
            vin="EDIT-VIN-2",
            equipment_type_id=type_a.id,
            equipment_model_id=model_a.id,
        )
        db.add_all([first, second])
        db.commit()
        db.refresh(first)

        services.update_equipment(
            db,
            first,
            EquipmentUpdate(
                registration_number="EDIT-REG-10",
                vin="EDIT-VIN-10",
                equipment_type_id=type_b.id,
                equipment_model_id=model_b.id,
                acquisition_date=date(2026, 8, 17),
                notes="تم تعديل بيانات العتاد",
            ),
        )
        assert first.registration_number == "EDIT-REG-10"
        assert first.vin == "EDIT-VIN-10"
        assert first.equipment_type_id == type_b.id
        assert first.equipment_model_id == model_b.id
        assert first.acquisition_date == date(2026, 8, 17)
        assert first.notes == "تم تعديل بيانات العتاد"


        try:
            services.create_equipment(
                db,
                EquipmentCreate(
                    equipment_type_id=type_a.id,
                    equipment_model_id=model_b.id,
                    registration_number="EDIT-BAD-MODEL",
                ),
            )
        except ValueError as exc:
            assert "لا ينتمي" in str(exc)
        else:
            raise AssertionError("equipment was created with a model from another type")

        try:
            services.update_equipment(db, first, EquipmentUpdate(registration_number="EDIT-REG-2"))
        except ValueError as exc:
            assert "رقم التسجيل" in str(exc)
        else:
            raise AssertionError("duplicate registration number was accepted")

        try:
            services.update_equipment(db, first, EquipmentUpdate(vin="EDIT-VIN-2"))
        except ValueError as exc:
            assert "رقم الهيكل" in str(exc)
        else:
            raise AssertionError("duplicate VIN was accepted")
    finally:
        db.close()


def test_equipment_create_rejects_duplicate_registration_and_vin():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = Session()
    try:
        equipment_type = EquipmentType(name="نوع اختبار إنشاء المعدة", measurement_unit="km")
        db.add(equipment_type)
        db.flush()
        db.add(
            Equipment(
                asset_code="EQ-DUPLICATE-REG",
                registration_number="DUPLICATE-REG",
                vin="DUPLICATE-VIN",
                equipment_type_id=equipment_type.id,
            )
        )
        db.commit()

        duplicate_registration = EquipmentCreate(
            equipment_type_id=equipment_type.id,
            registration_number="DUPLICATE-REG",
            vin="UNIQUE-VIN",
        )
        try:
            services.create_equipment(db, duplicate_registration)
        except ValueError as exc:
            assert "رقم التسجيل" in str(exc)
        else:
            raise AssertionError("duplicate registration number was accepted")

        duplicate_vin = EquipmentCreate(
            equipment_type_id=equipment_type.id,
            registration_number="UNIQUE-REG",
            vin="DUPLICATE-VIN",
        )
        try:
            services.create_equipment(db, duplicate_vin)
        except ValueError as exc:
            assert "رقم الهيكل" in str(exc)
        else:
            raise AssertionError("duplicate VIN was accepted")

        assert db.query(Equipment).count() == 1
    finally:
        db.close()


def test_equipment_create_form_reports_duplicate_identifiers_without_server_error(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = Session()
    equipment_type = EquipmentType(name="نوع اختبار نموذج إنشاء العتاد", measurement_unit="km")
    db.add(equipment_type)
    db.flush()
    db.add(
        Equipment(
            asset_code="EQ-FORM-DUPLICATE",
            registration_number="FORM-DUPLICATE-REG",
            vin="FORM-DUPLICATE-VIN",
            equipment_type_id=equipment_type.id,
        )
    )
    db.commit()
    admin = User(
        id=1,
        username="admin",
        full_name="مدير الاختبار",
        hashed_password="unused",
        role="admin",
    )
    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "create_default_admin", lambda: None)
    monkeypatch.setattr(main, "security_warnings", lambda *_args: [])
    app = main.create_app()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: admin
    try:
        with TestClient(app) as client:
            valid = client.post(
                "/equipment/create",
                data={
                    "equipment_type_id": equipment_type.id,
                    "registration_number": "FORM-NEW-REG",
                    "vin": "FORM-NEW-VIN",
                },
                follow_redirects=False,
            )
            assert valid.status_code == 303
            assert db.query(Equipment).filter_by(registration_number="FORM-NEW-REG").count() == 1

            duplicate_registration = client.post(
                "/equipment/create",
                data={
                    "equipment_type_id": equipment_type.id,
                    "registration_number": "FORM-DUPLICATE-REG",
                    "vin": "FORM-UNIQUE-VIN",
                },
                follow_redirects=False,
            )
            assert duplicate_registration.status_code == 303
            assert "رقم التسجيل مستخدم بالفعل" in unquote(
                duplicate_registration.headers["location"]
            )

            duplicate_vin = client.post(
                "/equipment/create",
                data={
                    "equipment_type_id": equipment_type.id,
                    "registration_number": "FORM-UNIQUE-REG",
                    "vin": "FORM-DUPLICATE-VIN",
                },
                follow_redirects=False,
            )
            assert duplicate_vin.status_code == 303
            assert "رقم الهيكل مستخدم بالفعل" in unquote(
                duplicate_vin.headers["location"]
            )
            assert db.query(Equipment).count() == 2
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_equipment_mutations_enforce_role_boundaries(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = Session()
    equipment_type = EquipmentType(name="نوع اختبار صلاحيات العتاد", measurement_unit="km")
    db.add(equipment_type)
    db.flush()
    model = EquipmentModel(name="طراز اختبار صلاحيات العتاد", equipment_type_id=equipment_type.id)
    db.add(model)
    db.flush()
    equipment = Equipment(
        asset_code="EQ-ROLE-TEST",
        registration_number="ROLE-TEST-REG",
        equipment_type_id=equipment_type.id,
        equipment_model_id=model.id,
    )
    viewer = User(
        id=20,
        username="equipment-viewer",
        full_name="قارئ اختبار",
        hashed_password="unused",
        role="viewer",
    )
    manager = User(
        id=21,
        username="equipment-manager",
        full_name="مدير اختبار",
        hashed_password="unused",
        role="fleet_manager",
    )
    operator = User(
        id=22,
        username="equipment-operator",
        full_name="مشغل اختبار",
        hashed_password="unused",
        role="operator",
    )
    db.add_all([equipment, viewer, manager, operator])
    db.commit()

    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "create_default_admin", lambda: None)
    monkeypatch.setattr(main, "security_warnings", lambda *_args: [])
    monkeypatch.setattr(settings, "DEV_DISABLE_AUTH", False)
    app = main.create_app()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: viewer
    try:
        with TestClient(app) as client:
            page = client.get("/equipment")
            assert page.status_code == 200
            assert 'id="equipmentCreateForm"' not in page.text
            assert 'id="equipmentImportDialog"' not in page.text
            assert 'href="/equipment/1/edit"' not in page.text
            assert client.get("/equipment/1/edit").status_code == 403
            detail = client.get("/equipment/1")
            assert detail.status_code == 200
            assert 'href="/equipment/1/edit"' not in detail.text
            assert 'action="/equipment/1/delete"' not in detail.text
            meter_page = client.get("/equipment/1/meters")
            assert meter_page.status_code == 200
            assert ".meter-table th:last-child,.meter-table td:last-child{display:none}" in meter_page.text

            create = client.post(
                "/equipment/create",
                data={
                    "equipment_type_id": equipment_type.id,
                    "equipment_model_id": model.id,
                    "registration_number": "VIEWER-CREATE",
                    "vin": "VIEWER-CREATE-VIN",
                },
                follow_redirects=False,
            )
            edit = client.post(
                f"/equipment/{equipment.id}/edit",
                data={
                    "equipment_type_id": equipment_type.id,
                    "equipment_model_id": model.id,
                    "registration_number": equipment.registration_number,
                    "vin": "",
                },
                follow_redirects=False,
            )
            preview = client.post(
                "/equipment/import/preview",
                files={"file": ("viewer.xlsx", b"not-an-xlsx", "application/octet-stream")},
            )
            confirm = client.post(
                "/equipment/import/confirm",
                files={"file": ("viewer.xlsx", b"not-an-xlsx", "application/octet-stream")},
            )
            meter_create = client.post(
                f"/equipment/{equipment.id}/meters/create",
                data={"reading_date": "2026-01-02", "odometer": "10"},
                follow_redirects=False,
            )
            meter_update = client.post(
                f"/equipment/{equipment.id}/meters/99/update",
                data={"reading_date": "2026-01-02", "odometer": "10"},
                follow_redirects=False,
            )
            meter_delete = client.post(
                f"/equipment/{equipment.id}/meters/99/delete",
                follow_redirects=False,
            )

            assert [response.status_code for response in (
                create, edit, preview, confirm, meter_create, meter_update, meter_delete,
            )] == [403] * 7
            assert db.query(Equipment).count() == 1
            assert db.query(Equipment).filter_by(id=equipment.id).one().registration_number == "ROLE-TEST-REG"

            app.dependency_overrides[get_current_user] = lambda: manager
            manager_page = client.get("/equipment")
            assert manager_page.status_code == 200
            assert 'id="equipmentCreateForm"' in manager_page.text
            manager_create = client.post(
                "/equipment/create",
                data={
                    "equipment_type_id": equipment_type.id,
                    "equipment_model_id": model.id,
                    "registration_number": "MANAGER-CREATE",
                    "first_service_date": "2020-01-02",
                },
                follow_redirects=False,
            )
            assert manager_create.status_code == 303
            assert db.query(Equipment).filter_by(registration_number="MANAGER-CREATE").count() == 1

            app.dependency_overrides[get_current_user] = lambda: operator
            operator_create = client.post(
                "/equipment/create",
                data={
                    "equipment_type_id": equipment_type.id,
                    "equipment_model_id": model.id,
                    "registration_number": "OPERATOR-CREATE",
                },
                follow_redirects=False,
            )
            assert operator_create.status_code == 403
            assert db.query(Equipment).filter_by(registration_number="OPERATOR-CREATE").count() == 0

            meter_create = client.post(
                f"/equipment/{equipment.id}/meters/create",
                data={"reading_date": "2026-01-02", "odometer": "10"},
                follow_redirects=False,
            )
            assert meter_create.status_code == 302
            reading = db.query(MeterReading).one()
            meter_update = client.post(
                f"/equipment/{equipment.id}/meters/{reading.id}/update",
                data={"reading_date": "2026-01-02", "odometer": "20"},
                follow_redirects=False,
            )
            assert meter_update.status_code == 302
            assert db.query(MeterReading).one().odometer == 20
            meter_delete = client.post(
                f"/equipment/{equipment.id}/meters/{reading.id}/delete",
                follow_redirects=False,
            )
            assert meter_delete.status_code == 302
            assert db.query(MeterReading).count() == 0
            assert db.query(MeterReadingChange).filter_by(action="delete").count() == 1
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_meter_reading_mutations_require_operator_role(monkeypatch):
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = Session()
    equipment_type = EquipmentType(name="نوع اختبار صلاحيات العداد", measurement_unit="km")
    db.add(equipment_type)
    db.flush()
    model = EquipmentModel(name="طراز اختبار صلاحيات العداد", equipment_type_id=equipment_type.id)
    db.add(model)
    db.flush()
    equipment = Equipment(
        asset_code="EQ-METER-ROLE-TEST",
        registration_number="METER-ROLE-TEST",
        equipment_type_id=equipment_type.id,
        equipment_model_id=model.id,
    )
    viewer = User(
        id=30,
        username="meter-viewer",
        full_name="قارئ اختبار",
        hashed_password="unused",
        role="viewer",
    )
    operator = User(
        id=31,
        username="meter-operator",
        full_name="مشغل اختبار",
        hashed_password="unused",
        role="operator",
    )
    db.add_all([equipment, viewer, operator])
    db.commit()
    db.refresh(equipment)
    reading = meter_services.create_reading(
        db,
        equipment_id=equipment.id,
        odometer=10,
        reading_date=datetime(2026, 1, 1),
    )

    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "create_default_admin", lambda: None)
    monkeypatch.setattr(main, "security_warnings", lambda *_args: [])
    monkeypatch.setattr(settings, "DEV_DISABLE_AUTH", False)
    app = main.create_app()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: viewer
    try:
        with TestClient(app) as client:
            page = client.get("/meter-readings")
            assert page.status_code == 200
            assert "＋ إضافة قراءة" not in page.text
            assert "⇧ استيراد ملف Excel" not in page.text
            assert 'id="readingForm"' not in page.text

            history = client.get(f"/meter-readings/history/{equipment.id}")
            assert history.status_code == 200
            assert 'class="action-btn edit"' not in history.text
            assert 'class="action-btn delete"' not in history.text
            assert 'id="editReadingModal"' not in history.text

            denied = [
                client.post(
                    "/meter-readings/create",
                    data={
                        "equipment_id": equipment.id,
                        "reading_date": "2026-01-02",
                        "value": "20",
                    },
                ),
                client.post("/meter-readings/bulk-create", json={"rows": []}),
                client.post(
                    "/meter-readings/import-excel",
                    files={"file": ("readings.xlsx", b"invalid", "application/octet-stream")},
                ),
                client.post(
                    "/meter-readings/import-excel-preview",
                    files={"file": ("readings.xlsx", b"invalid", "application/octet-stream")},
                ),
                client.post(
                    f"/meter-readings/history/{equipment.id}/update",
                    data={
                        "reading_id": reading.id,
                        "reading_date": "2026-01-01",
                        "value": "20",
                    },
                ),
                client.post(
                    f"/meter-readings/history/{equipment.id}/delete",
                    data={"reading_id": reading.id},
                ),
            ]
            assert [response.status_code for response in denied] == [403] * 6
            assert db.query(MeterReading).filter_by(equipment_id=equipment.id).count() == 1
            assert db.get(MeterReading, reading.id).odometer == 10
            assert db.query(MeterReadingChange).filter_by(action="delete").count() == 0

            app.dependency_overrides[get_current_user] = lambda: operator
            operator_page = client.get("/meter-readings")
            assert "＋ إضافة قراءة" in operator_page.text
            assert 'id="readingForm"' in operator_page.text
            operator_history = client.get(f"/meter-readings/history/{equipment.id}")
            assert 'class="action-btn edit"' in operator_history.text
            assert 'class="action-btn delete"' in operator_history.text

            created = client.post(
                "/meter-readings/create",
                data={
                    "equipment_id": equipment.id,
                    "reading_date": "2026-01-02",
                    "value": "20",
                },
            )
            assert created.status_code == 200
            reading_id = created.json()["reading_id"]
            assert db.get(MeterReading, reading_id).odometer == 20

            updated = client.post(
                f"/meter-readings/history/{equipment.id}/update",
                data={
                    "reading_id": reading_id,
                    "reading_date": "2026-01-02",
                    "value": "30",
                },
            )
            assert updated.status_code == 200
            assert db.get(MeterReading, reading_id).odometer == 30

            deleted = client.post(
                f"/meter-readings/history/{equipment.id}/delete",
                data={"reading_id": reading_id},
            )
            assert deleted.status_code == 200
            assert db.get(MeterReading, reading_id) is None
            change = db.query(MeterReadingChange).filter_by(action="delete").one()
            assert change.actor_id == operator.id

            nested_reading = meter_services.create_reading(
                db,
                equipment_id=equipment.id,
                odometer=20,
                reading_date=datetime(2026, 1, 2),
            )
            duplicate_day = client.post(
                f"/equipment/{equipment.id}/meters/{nested_reading.id}/update",
                data={"reading_date": "2026-01-01", "odometer": "15"},
                follow_redirects=False,
            )
            assert duplicate_day.status_code == 400
            db.refresh(nested_reading)
            assert nested_reading.reading_date == datetime(2026, 1, 2)
            assert nested_reading.odometer == 20
    finally:
        app.dependency_overrides.clear()
        db.close()
