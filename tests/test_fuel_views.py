from io import BytesIO
from datetime import date

from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.dependencies import get_current_user
from app.database import model_registry  # noqa: F401
from app.database import session as session_module
from app.database.base import Base
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentBrand, EquipmentModel, EquipmentType
from app.modules.fuel.model_rate_import import MODEL_RATE_HEADERS
from app.modules.fuel.models import FuelModelConsumptionRate
from app.modules.users.models import User
from web import main


def test_fuel_views_and_model_rate_excel_import(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine, autoflush=False)
    Base.metadata.create_all(engine)

    db = testing_session()
    user = User(username="fuel-view-test", full_name="اختبار", hashed_password="unused", role="ADMIN")
    equipment_type = EquipmentType(name="نوع اختبار الوقود", measurement_unit="km")
    brand = EquipmentBrand(name="علامة اختبار الوقود")
    db.add_all([user, equipment_type, brand])
    db.flush()
    model = EquipmentModel(name="طراز اختبار الوقود", equipment_type_id=equipment_type.id, brand_id=brand.id)
    db.add(model)
    db.flush()
    equipment = Equipment(
        asset_code="FUEL-VIEW-1",
        registration_number="FUEL-VIEW-1",
        equipment_type_id=equipment_type.id,
        equipment_model_id=model.id,
        operational_status="available",
    )
    db.add(equipment)
    db.commit()
    user_id = user.id
    equipment_id = equipment.id
    model_id = model.id
    db.close()

    def override_get_db():
        session = testing_session()
        try:
            yield session
        finally:
            session.close()

    def override_current_user():
        session = testing_session()
        try:
            yield session.get(User, user_id)
        finally:
            session.close()

    with monkeypatch.context() as patch:
        patch.setattr(main, "init_db", lambda: None)
        patch.setattr(main, "create_default_admin", lambda: None)
        patch.setattr(session_module, "SessionLocal", testing_session)
        app = main.create_app()
        app.dependency_overrides[session_module.get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_current_user
        with TestClient(app) as client:
            battery_page = client.get("/batteries")
            assert battery_page.status_code == 200
            assert 'id="batteryStatDialog"' in battery_page.text
            assert 'data-battery-stat="installed"' in battery_page.text
            assert 'data-battery-stat="total"' not in battery_page.text
            assert "الإجمالي · عرض الكل" not in battery_page.text
            assert "وثيقة الاستلام" in battery_page.text
            assert "لا توجد بطاريات مسجلة حاليًا." in battery_page.text
            empty_indicator_table = client.get("/batteries?filter=installed")
            assert empty_indicator_table.status_code == 200
            assert "لا توجد بطاريات مسجلة حاليًا." in empty_indicator_table.text

            fuel_page = client.get("/fuel")
            assert fuel_page.status_code == 200
            assert 'name="model_id"' in fuel_page.text
            assert 'name="equipment_id"' in fuel_page.text
            assert '<select id="fuelType" name="fuel_type" required>' in fuel_page.text
            assert "الطراز" in fuel_page.text and "رقم التسجيل" in fuel_page.text

            form_data = {
                "model_id": str(model_id + 1),
                "equipment_id": str(equipment_id),
                "fueling_date": date.today().isoformat(),
                "meter_value": "1000",
                "quantity": "20",
                "fuel_type": "ديزل",
            }
            mismatched_model = client.post("/fuel", data=form_data)
            assert mismatched_model.status_code == 400
            form_data["model_id"] = str(model_id)
            form_data["fuel_type"] = "نوع غير معتمد"
            invalid_fuel_type = client.post("/fuel", data=form_data)
            assert invalid_fuel_type.status_code == 400
            form_data["fuel_type"] = "ديزل"
            saved_fuel = client.post("/fuel", data=form_data, follow_redirects=False)
            assert saved_fuel.status_code == 303

            rates_template = client.get("/fuel/model-rates/template.xlsx")
            assert rates_template.status_code == 200
            workbook = load_workbook(BytesIO(rates_template.content), read_only=True)
            sheet = workbook["معدلات الاستهلاك"]
            assert tuple(cell.value for cell in next(sheet.iter_rows())) == MODEL_RATE_HEADERS
            workbook.close()
            workbook = load_workbook(BytesIO(rates_template.content))
            sheet = workbook["معدلات الاستهلاك"]
            assert sheet.freeze_panes == "A2"
            assert sheet.data_validations.count == 4
            assert workbook.defined_names.get("FuelTypes") is not None
            workbook.close()

            imported = BytesIO()
            workbook = load_workbook(BytesIO(rates_template.content))
            sheet = workbook["معدلات الاستهلاك"]
            sheet.append(("علامة اختبار الوقود", "طراز اختبار الوقود", "ديزل", 12.5, "لتر/100 كم"))
            workbook.save(imported)
            workbook.close()
            response = client.post(
                "/fuel/model-rates/import",
                files={"file": ("fuel-rates.xlsx", imported.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                follow_redirects=True,
            )
            assert response.status_code == 200
            assert "تم استيراد أو تحديث 1 معدل استهلاك" in response.text
            assert "12.50" in response.text or "12.5" in response.text

            equipment_list = client.get("/fuel/equipment")
            assert equipment_list.status_code == 200
            assert "FUEL-VIEW-1" in equipment_list.text
            assert "/equipment/1/fuel" in equipment_list.text
            equipment_history = client.get(f"/equipment/{equipment_id}/fuel")
            assert equipment_history.status_code == 200

        verify = testing_session()
        assert verify.query(FuelModelConsumptionRate).count() == 1
        verify.close()
        app.dependency_overrides.clear()
    engine.dispose()
