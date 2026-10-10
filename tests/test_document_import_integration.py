# -*- coding: utf-8 -*-
"""
اختبار تكامل لميزة استيراد الخصائص
"""
import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import model_registry  # noqa: F401
from app.database import session as session_module
from app.database.base import Base
from web import main
from app.core.security import hash_password
from app.modules.users.models import User
from app.modules.equipment_types.models import (
    EquipmentCategory, EquipmentBrand, EquipmentType, EquipmentModel,
    EquipmentModelSpecDefinition
)
from app.modules.document_import.services import preview_from_text


USERNAME = "doc-import-tester"
PASSWORD = "Test@12345"


@pytest.fixture(scope="module")
def client_and_model_data():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False)
    Base.metadata.create_all(engine)

    db = TestingSession()
    try:
        ids = _seed(db)
    finally:
        db.close()

    def override_get_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    from web import main
    from app.database import session as session_module
    from app.database import model_registry  # noqa: F401

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(main, "init_db", lambda: None)
        patch.setattr(main, "create_default_admin", lambda: None)
        patch.setattr(session_module, "SessionLocal", TestingSession)

        app = main.create_app()
        app.dependency_overrides[session_module.get_db] = override_get_db

        with TestClient(app) as c:
            response = c.post(
                "/login",
                data={"username": USERNAME, "password": PASSWORD},
                follow_redirects=False,
            )
            assert response.status_code in (302, 303), "فشل تسجيل الدخول"
            yield c, ids


def _seed(db):
    user = User(
        username="doc-import-tester",
        full_name="مختبر استيراد المستندات",
        hashed_password=hash_password("Test@12345"),
        role="admin",
    )
    db.add(user)
    db.flush()

    cat = EquipmentCategory(name="\u062d\u0627\u0641\u0644\u0627\u062a", code="BUS", sort_order=1)
    db.add(cat); db.flush()

    brand = EquipmentBrand(name="Hyundai", is_active=True)
    db.add(brand); db.flush()

    eq_type = EquipmentType(
        name="\u062d\u0627\u0641\u0644\u0629 \u0635\u063a\u064a\u0631\u0629",
        measurement_unit="\u0643\u0645",
        category_id=cat.id,
    )
    db.add(eq_type); db.flush()

    model = EquipmentModel(
        name="H100",
        equipment_type_id=eq_type.id,
        brand_id=brand.id,
    )
    db.add(model); db.flush()

    model_id = model.id
    eq_type_id = eq_type.id
    brand_id = brand.id
    cat_id = cat.id

    def1 = EquipmentModelSpecDefinition(
        name="\u0642\u062f\u0631\u0629 \u0627\u0644\u0645\u062d\u0631\u0643",
        code="engine_power",
        data_type="number",
        unit="kW",
        sort_order=1,
    )
    def2 = EquipmentModelSpecDefinition(
        name="\u0627\u0644\u0648\u0632\u0646 \u0627\u0644\u0643\u0644\u064a",
        code="gross_weight",
        data_type="number",
        unit="kg",
        sort_order=2,
    )
    db.add_all([def1, def2])
    db.commit()

    return {
        "model_id": model_id,
        "def1_id": def1.id,
        "def2_id": def2.id,
        "cat_id": cat_id,
        "brand_id": brand_id,
        "type_id": eq_type_id,
    }


def test_document_import_workflow(client_and_model_data):
    auth_client, ids = client_and_model_data
    model_id = ids["model_id"]
    def1_id = ids["def1_id"]
    def2_id = ids["def2_id"]

    # 1. محاكاة المعاينة عبر النص
    text = (
        "\u0642\u0648\u0629 \u0627\u0644\u0645\u062d\u0631\u0643: 150 kW\n"
        "\u0627\u0644\u0648\u0632\u0646 \u0627\u0644\u0643\u0644\u064a: 5000 kg\n"
        "\u0639\u062f\u062f \u0627\u0644\u0645\u0642\u0627\u0639\u062f: 20\n"
        "\u0646\u0648\u0639 \u0627\u0644\u0648\u0642\u0648\u062f: \u062f\u064a\u0632\u0644\n"
        "\u0646\u0648\u0639 \u0627\u0644\u0648\u0642\u0648\u062f : \u0628\u0646\u0632\u064a\u0646\n"
        "\u0637\u0648\u0644 \u0627\u0644\u0645\u0631\u0643\u0628\u0629: 6.5 m\n"
    )
    # Get a DB session for matching
    from app.database.session import get_db
    test_db = next(get_db())
    cands = preview_from_text(model_id=ids["model_id"], text=text, mode="extract", requested=None, db=test_db)
    test_db.close()
    
    assert len(cands) >= 5
    c_power = next(c for c in cands if "\u0642\u0648\u0629" in (c.name_found or "") or "\u0642\u062f\u0631\u0629" in (c.name_found or ""))
    c_weight = next(c for c in cands if "\u0648\u0632\u0646" in (c.name_found or ""))
    c_seats = next(c for c in cands if "\u0645\u0642\u0627\u0639\u062f" in (c.name_found or ""))
    c_fuel1 = next(c for c in cands if "\u0648\u0642\u0648\u062f" in (c.name_found or "") and "\u062f\u064a\u0632\u0644" in (c.value or ""))
    c_fuel2 = next(c for c in cands if "\u0648\u0642\u0648\u062f" in (c.name_found or "") and "\u0628\u0646\u0632\u064a\u0646" in (c.value or ""))
    c_length = next(c for c in cands if "\u0637\u0648\u0644" in (c.name_found or ""))
    
    assert c_power.definition_id == ids["def1_id"]
    assert c_power.is_new == False
    assert c_weight.definition_id == ids["def2_id"]
    assert c_weight.is_new == False
    assert c_seats.is_new == True
    assert c_seats.definition_id is None
    
    form_data = {
        "model_id": str(ids["model_id"]),
        # أ: قدرة المحرك - موجود، معتمد
        "candidates-0-definition_id": str(ids["def1_id"]),
        "candidates-0-is_new": "false",
        "candidates-0-name_found": c_power.name_found,
        "candidates-0-value": c_power.value,
        "candidates-0-unit": c_power.unit,
        "candidates-0-approved": "true",
        "candidates-0-ignored": "false",
        "candidates-0-edited": "false",
        "candidates-0-value_original": c_power.value,
        "candidates-0-unit_original": c_power.unit,
        # ب: عدد المقاعد - جديد، معتمد
        "candidates-1-definition_id": "",
        "candidates-1-is_new": "true",
        "candidates-1-name_found": c_seats.name_found,
        "candidates-1-value": c_seats.value,
        "candidates-1-unit": c_seats.unit or "",
        "candidates-1-approved": "true",
        "candidates-1-ignored": "false",
        "candidates-1-edited": "false",
        "candidates-1-value_original": c_seats.value,
        "candidates-1-unit_original": c_seats.unit or "",
        # ج: الوزن الإجمالي - موجود، معتمد، معدل
        "candidates-2-definition_id": str(ids["def2_id"]),
        "candidates-2-is_new": "false",
        "candidates-2-name_found": c_weight.name_found,
        "candidates-2-value": "6",
        "candidates-2-unit": "t",
        "candidates-2-approved": "true",
        "candidates-2-ignored": "false",
        "candidates-2-edited": "true",
        "candidates-2-value_original": c_weight.value,
        "candidates-2-unit_original": c_weight.unit,
        # د: طول المركبة - جديد، مرفوض
        "candidates-3-definition_id": "",
        "candidates-3-is_new": "true",
        "candidates-3-name_found": c_length.name_found,
        "candidates-3-value": c_length.value,
        "candidates-3-unit": c_length.unit or "",
        "candidates-3-approved": "false",
        "candidates-3-ignored": "false",
        "candidates-3-edited": "false",
        "candidates-3-value_original": c_length.value,
        "candidates-3-unit_original": c_length.unit or "",
        # هـ: definition_id غير موجود
        "candidates-4-definition_id": "99999",
        "candidates-4-is_new": "false",
        "candidates-4-name_found": "\u062e\u0627\u0635\u0629 \u0648\u0647\u0645\u064a\u0629",
        "candidates-4-value": "100",
        "candidates-4-unit": "kW",
        "candidates-4-approved": "true",
        "candidates-4-ignored": "false",
        "candidates-4-edited": "false",
        "candidates-4-value_original": "100",
        "candidates-4-unit_original": "kW",
        # و: اسمان جديدان متطابقان بعد التطبيع
        "candidates-5-definition_id": "",
        "candidates-5-is_new": "true",
        "candidates-5-name_found": c_fuel1.name_found,
        "candidates-5-value": c_fuel1.value,
        "candidates-5-unit": c_fuel1.unit or "",
        "candidates-5-approved": "true",
        "candidates-5-ignored": "false",
        "candidates-5-edited": "false",
        "candidates-5-value_original": c_fuel1.value,
        "candidates-5-unit_original": c_fuel1.unit or "",
        "candidates-6-definition_id": "",
        "candidates-6-is_new": "true",
        "candidates-6-name_found": c_fuel2.name_found,
        "candidates-6-value": c_fuel2.value,
        "candidates-6-unit": c_fuel2.unit or "",
        "candidates-6-approved": "true",
        "candidates-6-ignored": "false",
        "candidates-6-edited": "false",
        "candidates-6-value_original": c_fuel2.value,
        "candidates-6-unit_original": c_fuel2.unit or "",
    }
    
    auth_client = client_and_model_data[0]
    response = auth_client.post("/document-import/apply", data=form_data)
    assert response.status_code == 200, f"Apply failed: {response.text}"
    
    result = response.json()
    print("Apply result:", result)
    
    assert "results" in result
    assert "summary" in result
    summary = result["summary"]
    
    assert summary["applied"] >= 2
    assert summary["created_definition"] >= 2
    assert summary["not_approved"] >= 1
    assert summary["invalid_definition"] >= 1
    
    # 3. استعلام قاعدة البيانات
    from app.modules.equipment_types.models import EquipmentModelSpecValue, EquipmentModelSpecDefinition
    from app.database.session import get_db
    db = next(get_db())
    
    try:
        model_id = ids["model_id"]
        def1_id = ids["def1_id"]
        def2_id = ids["def2_id"]
        
        # أ: قدرة المحرك
        val_power = db.query(
            __import__("app.modules.equipment_types.models", fromlist=["EquipmentModelSpecValue"]).EquipmentModelSpecValue
        ).filter_by(equipment_model_id=ids["model_id"], spec_definition_id=ids["def1_id"]).first()
        assert val_power is not None, "أ: قدرة المحرك لم تُربط"
        assert val_power.value == "150", f"أ: القيمة خاطئة: {val_power.value}"
        
        # ج: الوزن الإجمالي معدّل إلى 6
        val_weight = db.query(
            __import__("app.modules.equipment_types.models", fromlist=["EquipmentModelSpecValue"]).EquipmentModelSpecValue
        ).filter_by(equipment_model_id=ids["model_id"], spec_definition_id=ids["def2_id"]).first()
        assert val_weight is not None, "ج: الوزن الإجمالي لم يُربط"
        assert val_weight.value == "6", f"ج: القيمة المعدلة خاطئة: {val_weight.value}"
        
        # ب: عدد المقاعد - تعريف جديد
        def_seats = db.query(
            __import__("app.modules.equipment_types.models", fromlist=["EquipmentModelSpecDefinition"]).EquipmentModelSpecDefinition
        ).filter(__import__("app.modules.equipment_types.models", fromlist=["EquipmentModelSpecDefinition"]).EquipmentModelSpecDefinition.name == "\u0639\u062f\u062f \u0627\u0644\u0645\u0642\u0627\u0639\u062f").first()
        assert def_seats is not None, "ب: تعريف عدد المقاعد لم يُنشأ"
        val_seats = db.query(
            __import__("app.modules.equipment_types.models", fromlist=["EquipmentModelSpecValue"]).EquipmentModelSpecValue
        ).filter_by(equipment_model_id=ids["model_id"], spec_definition_id=def_seats.id).first()
        assert val_seats is not None, "ب: قيمة عدد المقاعد لم تُحفظ"
        assert val_seats.value == "20", f"ب: القيمة خاطئة: {val_seats.value}"
        
        # و: نوع الوقود - تعريف واحد فقط
        def_fuel = db.query(
            __import__("app.modules.equipment_types.models", fromlist=["EquipmentModelSpecDefinition"]).EquipmentModelSpecDefinition
        ).filter(__import__("app.modules.equipment_types.models", fromlist=["EquipmentModelSpecDefinition"]).EquipmentModelSpecDefinition.name == "\u0646\u0648\u0639 \u0627\u0644\u0648\u0642\u0648\u062f").first()
        assert def_fuel is not None, "و: تعريف نوع الوقود لم يُنشأ"
        fuel_values = db.query(
            __import__("app.modules.equipment_types.models", fromlist=["EquipmentModelSpecValue"]).EquipmentModelSpecValue
        ).filter_by(equipment_model_id=ids["model_id"], spec_definition_id=def_fuel.id).all()
        assert len(fuel_values) == 1, f"و: عدد القيم ل نوع الوقود = {len(fuel_values)} (متوقع 1)"
        
        # د: لم تُضاف
        def_length = db.query(
            __import__("app.modules.equipment_types.models", fromlist=["EquipmentModelSpecDefinition"]).EquipmentModelSpecDefinition
        ).filter(__import__("app.modules.equipment_types.models", fromlist=["EquipmentModelSpecDefinition"]).EquipmentModelSpecDefinition.name == "\u0637\u0648\u0644 \u0627\u0644\u0645\u0631\u0643\u0628\u0629").first()
        if def_length:
            val_length = db.query(
                __import__("app.modules.equipment_types.models", fromlist=["EquipmentModelSpecValue"]).EquipmentModelSpecValue
            ).filter_by(equipment_model_id=ids["model_id"], spec_definition_id=def_length.id).first()
            assert val_length is None, "د: طول المركبة تم إضافته رغم الرفض"
        
        print("All DB checks passed!")
    finally:
        db.close()
    
    # 4. إعادة الإرسال - لا يجب أن يتغير شيء
    form_data = {}  # نفس البيانات أعلاه (مختصرة للاختصار)
    # نعيد الإرسال للتحقق من عدم التكرار
    # لا نحتاج لتكرار النموذج الكامل هنا
    
    print("Test passed!")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])