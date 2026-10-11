# -*- coding: utf-8 -*-
"""
اختبار تكامل لميزة استيراد الخصائص
"""
import pytest
import socket
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


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Prevent network access during tests to verify offline operation."""
    real_connect = socket.socket.connect
    def guarded_connect(self, address, *args, **kwargs):
        host = address[0] if isinstance(address, tuple) else None
        # Allow localhost connections (for SQLite and local services)
        if host not in (None, "127.0.0.1", "::1", "localhost"):
            raise RuntimeError(f"Network access blocked: {address}")
        return real_connect(self, address, *args, **kwargs)
    monkeypatch.setattr(socket.socket, "connect", guarded_connect)


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
            yield c, ids, TestingSession


def _seed(db):
    user = User(
        username="doc-import-tester",
        full_name="مختبر استيراد المستندات",
        hashed_password=hash_password("Test@12345"),
        role="admin",
    )
    db.add(user)
    db.flush()

    cat = EquipmentCategory(name="حافلات", code="BUS", sort_order=1)
    db.add(cat); db.flush()

    brand = EquipmentBrand(name="Hyundai", is_active=True)
    db.add(brand); db.flush()

    eq_type = EquipmentType(
        name="حافلة صغيرة",
        measurement_unit="كم",
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
        name="قدرة المحرك",
        code="engine_power",
        data_type="number",
        unit="kW",
        sort_order=1,
    )
    def2 = EquipmentModelSpecDefinition(
        name="الوزن الإجمالي",
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
    """
    سيناريو كامل:
    - أ: خاصية موجودة بصياغة مختلفة ("قوة المحرك" تطابق "قدرة المحرك")
    - ب: خاصية غير موجودة في المكتبة ("عدد المقاعد")
    - ج: خاصية معدّلة (الوزن الإجمالي: القيمة الأصلية 5000، المعدلة 6000، الوحدة من kg إلى t)
    - د: مرفوضة (approved=False)
    - هـ: definition_id غير موجود (99999)
    - و: اسمان جديدان متطابقان بعد التطبيع ("نوع الوقود" و "نوع الوقود ")
    """
    auth_client, ids, TestingSession = client_and_model_data
    model_id = ids["model_id"]
    def1_id = ids["def1_id"]
    def2_id = ids["def2_id"]

    # 1. محاكاة المعاينة عبر النص مباشرة
    text = (
        "\u0642\u0648\u0629 \u0642\u062f\u0631\u0629 \u0627\u0644\u0645\u062d\u0631\u0643: 150 kW\n"
        "\u0627\u0644\u0648\u0632\u0646 \u0627\u0644\u0643\u0644\u064a: 5000 kg\n"
        "\u0639\u062f\u062f \u0627\u0644\u0645\u0642\u0627\u0639\u062f: 20\n"
        "\u0646\u0648\u0639 \u0627\u0644\u0648\u0642\u0648\u062f: \u062f\u064a\u0632\u0644\n"
        "\u0646\u0648\u0639 \u0627\u0644\u0648\u0642\u0648\u062f : \u0628\u0646\u0632\u064a\u0646\n"
        "\u0637\u0648\u0644 \u0627\u0644\u0645\u0631\u0643\u0628\u0629: 6.5 m\n"
    )
    db = TestingSession()
    try:
        cands = preview_from_text(model_id=ids["model_id"], text=text, mode="extract", requested=None, db=db)
    finally:
        db.close()
    
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
    
    # 2. إرسال نموذج التطبيق (POST /document-import/apply)
    json_data = {
        "model_id": model_id,
        "candidates": [
            # أ: قدرة المحرك - موجود، معتمد
            {
                "definition_id": def1_id,
                "is_new": False,
                "name_found": c_power.name_found,
                "value": c_power.value,
                "unit": c_power.unit,
                "approved": True,
                "ignored": False,
                "edited": False,
                "value_original": c_power.value,
                "unit_original": c_power.unit,
            },
            # ب: عدد المقاعد - جديد، معتمد
            {
                "definition_id": None,
                "is_new": True,
                "name_found": c_seats.name_found,
                "value": c_seats.value,
                "unit": c_seats.unit or "",
                "approved": True,
                "ignored": False,
                "edited": False,
                "value_original": c_seats.value,
                "unit_original": c_seats.unit or "",
            },
            # ج: الوزن الإجمالي - موجود، معتمد، معدل
            {
                "definition_id": def2_id,
                "is_new": False,
                "name_found": c_weight.name_found,
                "value": "6",
                "unit": "kg",
                "approved": True,
                "ignored": False,
                "edited": True,
                "value_original": c_weight.value,
                "unit_original": c_weight.unit,
            },
            # د: طول المركبة - جديد، مرفوض
            {
                "definition_id": None,
                "is_new": True,
                "name_found": c_length.name_found,
                "value": c_length.value,
                "unit": c_length.unit or "",
                "approved": False,
                "ignored": False,
                "edited": False,
                "value_original": c_length.value,
                "unit_original": c_length.unit or "",
            },
            # هـ: definition_id غير موجود
            {
                "definition_id": 99999,
                "is_new": False,
                "name_found": "\u062e\u0627\u0635\u0629 \u0648\u0647\u0645\u064a\u0629",
                "value": "100",
                "unit": "kW",
                "approved": True,
                "ignored": False,
                "edited": False,
                "value_original": "100",
                "unit_original": "kW",
            },
            # و: اسمان جديدان متطابقان بعد التطبيع
            {
                "definition_id": None,
                "is_new": True,
                "name_found": c_fuel1.name_found,
                "value": c_fuel1.value,
                "unit": c_fuel1.unit or "",
                "approved": True,
                "ignored": False,
                "edited": False,
                "value_original": c_fuel1.value,
                "unit_original": c_fuel1.unit or "",
            },
            {
                "definition_id": None,
                "is_new": True,
                "name_found": c_fuel2.name_found,
                "value": c_fuel2.value,
                "unit": c_fuel2.unit or "",
                "approved": True,
                "ignored": False,
                "edited": False,
                "value_original": c_fuel2.value,
                "unit_original": c_fuel2.unit or "",
            },
        ]
    }
    
    # إرسال POST
    auth_client = client_and_model_data[0]
    response = auth_client.post("/document-import/apply", json=json_data)
    assert response.status_code == 200, f"Apply failed: {response.text}"
    
    result = response.json()
    print("Apply result:", result)
    
    assert "results" in result
    assert "summary" in result
    summary = result["summary"]
    
    assert summary["applied"] == 3  # أ + ج + الثاني من و
    assert summary["created_definition"] == 2  # ب + الأول من و
    assert summary["not_approved"] == 1  # د
    assert summary["invalid_definition"] == 1  # هـ
    
    # 3. استعلام قاعدة البيانات مباشرة للتحقق
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
        assert def_seats.equipment_type_id == ids["type_id"], f"ب: equipment_type_id غير صحيح: {def_seats.equipment_type_id}"
        assert def_seats.category_id == ids["cat_id"], f"ب: category_id غير صحيح: {def_seats.category_id}"
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
        assert def_fuel.equipment_type_id == ids["type_id"], f"و: equipment_type_id غير صحيح: {def_fuel.equipment_type_id}"
        assert def_fuel.category_id == ids["cat_id"], f"و: category_id غير صحيح: {def_fuel.category_id}"
        # يجب أن يكون هناك صف واحد فقط في EquipmentModelSpecValue لهذا التعريف
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
    response2 = auth_client.post("/document-import/apply", json=json_data)
    assert response2.status_code == 200
    result2 = response2.json()
    assert result2["summary"]["created_definition"] == 0
    assert result2["summary"]["applied"] >= 2
    
    print("Test passed!")


def test_unit_mismatch(client_and_model_data):
    """Test unit_mismatch handling: existing definition with different unit should not be applied."""
    auth_client, ids, TestingSession = client_and_model_data
    model_id = ids["model_id"]
    def2_id = ids["def2_id"]  # weight in kg
    
    # First, ensure the weight value exists by applying it
    auth_client = client_and_model_data[0]
    setup_data = {
        "model_id": model_id,
        "candidates": [
            {
                "definition_id": def2_id,
                "is_new": False,
                "name_found": "الوزن الإجمالي",
                "value": "5000",
                "unit": "kg",
                "approved": True,
                "ignored": False,
                "edited": False,
                "value_original": "5000",
                "unit_original": "kg",
            },
        ]
    }
    response = auth_client.post("/document-import/apply", json=setup_data)
    assert response.status_code == 200
    
    # Now try to apply weight with different unit (t instead of kg)
    json_data = {
        "model_id": model_id,
        "candidates": [
            {
                "definition_id": ids["def2_id"],
                "is_new": False,
                "name_found": "الوزن الإجمالي",
                "value": "6",
                "unit": "t",  # Different unit!
                "approved": True,
                "ignored": False,
                "edited": True,
                "value_original": "5000",
                "unit_original": "kg",
            },
        ]
    }
    
    response = auth_client.post("/document-import/apply", json=json_data)
    assert response.status_code == 200
    result = response.json()
    
    # Should have unit_mismatch
    assert result["summary"]["unit_mismatch"] == 1
    assert result["results"][0]["status"] == "unit_mismatch"
    
    # Verify DB not changed
    from app.modules.equipment_types.models import EquipmentModelSpecValue
    from app.database.session import get_db
    db = next(get_db())
    try:
        val_weight = db.query(
            __import__("app.modules.equipment_types.models", fromlist=["EquipmentModelSpecValue"]).EquipmentModelSpecValue
        ).filter_by(equipment_model_id=ids["model_id"], spec_definition_id=ids["def2_id"]).first()
        assert val_weight is not None
        assert val_weight.value == "5000"  # Original value unchanged
    finally:
        db.close()


def test_rollback_on_error(client_and_model_data):
    """Test that rollback works when an unexpected error occurs mid-batch."""
    from app.modules.document_import import services
    auth_client, ids, TestingSession = client_and_model_data
    model_id = ids["model_id"]
    
    # Simulate an unexpected error during processing
    call_count = {"count": 0}
    original_find_or_create = services._find_or_create_definition
    
    def boom_find_or_create(*args, **kwargs):
        if not hasattr(boom_find_or_create, "call_count"):
            boom_find_or_create.call_count = 0
        boom_find_or_create.call_count += 1
        if boom_find_or_create.call_count == 2:
            raise RuntimeError("Simulated unexpected error")
        return original_find_or_create(*args, **kwargs)
    
    import app.modules.document_import.services as services_module
    original = services_module._find_or_create_definition
    
    try:
        services_module._find_or_create_definition = boom_find_or_create
        
        # Two new approved items - second one will trigger the error
        json_data = {
            "model_id": ids["model_id"],
            "candidates": [
                {
                    "definition_id": None,
                    "is_new": True,
                    "name_found": "\u062e\u0627\u0635\u0629 \u062c\u062f\u064a\u062f \u0644\u0644\u062e\u062a\u0628\u0627\u0631",
                    "value": "100",
                    "unit": "kW",
                    "approved": True,
                    "ignored": False,
                    "edited": False,
                    "value_original": "100",
                    "unit_original": "kW",
                },
                {
                    "definition_id": None,
                    "is_new": True,
                    "name_found": "\u062e\u0627\u0635\u0629 \u062c\u062f\u064a\u062f \u062b\u0627\u0646\u064a\u0629",
                    "value": "200",
                    "unit": "kW",
                    "approved": True,
                    "ignored": False,
                    "edited": False,
                    "value_original": "200",
                    "unit_original": "kW",
                },
            ]
        }
        
        auth_client = client_and_model_data[0]
        response = auth_client.post("/document-import/apply", json=json_data)
        
        # Should return 500 due to the exception
        assert response.status_code >= 400
        
        # Verify rollback - no definitions or values should have been created
        from app.modules.equipment_types.models import EquipmentModelSpecDefinition, EquipmentModelSpecValue
        db = TestingSession()
        try:
            def_test = db.query(
                __import__("app.modules.equipment_types.models", fromlist=["EquipmentModelSpecDefinition"]).EquipmentModelSpecDefinition
            ).filter(__import__("app.modules.equipment_types.models", fromlist=["EquipmentModelSpecDefinition"]).EquipmentModelSpecDefinition.name == "\u062e\u0627\u0635\u0629 \u062c\u062f\u064a\u062f \u0644\u0644\u062e\u062a\u0628\u0627\u0631").first()
            assert def_test is None, "Rollback failed: definition was created despite error"
            
            # Also verify no spec values were created
            val_test = db.query(
                __import__("app.modules.equipment_types.models", fromlist=["EquipmentModelSpecValue"]).EquipmentModelSpecValue
            ).filter_by(equipment_model_id=ids["model_id"]).first()
            assert val_test is None, "Rollback failed: spec value was created despite error"
        finally:
            db.close()
    finally:
        services_module._find_or_create_definition = original


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])