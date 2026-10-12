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
    EquipmentModelSpecDefinition, EquipmentModelSpecValue
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


# ----------------------------------------------------------------------------
# مساعدات مشتركة (الـ fixture على مستوى الوحدة: نستعمل أسماء فريدة وأعدادًا نسبية)
# ----------------------------------------------------------------------------
def cand(name, value, unit="", *, definition_id=None, is_new=False, approved=True,
         edited=False, value_edited=None, unit_edited=None):
    return {
        "definition_id": definition_id, "name_found": name, "value": value,
        "unit": unit or None, "is_new": is_new, "approved": approved, "ignored": False,
        "edited": edited, "value_edited": value_edited, "unit_edited": unit_edited,
    }


def counts(S):
    """(عدد التعريفات، عدد القيم)"""
    db = S()
    try:
        return (db.query(EquipmentModelSpecDefinition).count(),
                db.query(EquipmentModelSpecValue).count())
    finally:
        db.close()


def make_type(S, name, cat_id):
    db = S()
    try:
        t = EquipmentType(name=name, measurement_unit="كم", category_id=cat_id)
        db.add(t); db.commit()
        return t.id
    finally:
        db.close()


def make_def(S, name, unit, type_id, data_type="text", options=None):
    db = S()
    try:
        d = EquipmentModelSpecDefinition(
            name=name, unit=unit, data_type=data_type, options=options,
            sort_order=0, equipment_type_id=type_id,
        )
        db.add(d); db.commit()
        return d.id
    finally:
        db.close()


def apply_json(client, model_id, cands):
    return client.post("/document-import/apply", json={"model_id": model_id, "candidates": cands})


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

    d0, _ = counts(TestingSession)
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
    D, V = EquipmentModelSpecDefinition, EquipmentModelSpecValue
    assert counts(TestingSession)[0] == d0 + 2  # تعريفان جديدان فقط: عدد المقاعد + نوع الوقود
    after_first = counts(TestingSession)
    db = TestingSession()
    try:
        def value_rows(def_id):
            return db.query(V).filter_by(equipment_model_id=model_id, spec_definition_id=def_id).all()

        # أ: قدرة المحرك مربوطة بالتعريف الموجود دون تعريف مكرر
        rows = value_rows(def1_id)
        assert len(rows) == 1 and rows[0].value == "150"
        assert db.query(D).filter(D.code == "engine_power").count() == 1

        # ج: الوزن الإجمالي بالقيمة المعدّلة لا الأصلية
        rows = value_rows(def2_id)
        assert len(rows) == 1 and rows[0].value == "6"

        # ب: عدد المقاعد تعريف جديد واحد بنوع المعدة والفئة الصحيحين
        def_seats = db.query(D).filter(D.name == "عدد المقاعد").one()
        assert def_seats.equipment_type_id == ids["type_id"]
        assert def_seats.category_id == ids["cat_id"]
        rows = value_rows(def_seats.id)
        assert len(rows) == 1 and rows[0].value == "20"

        # و: نوع الوقود تعريف واحد وقيمة واحدة للاسمين المتطابقين بعد التطبيع
        def_fuel = db.query(D).filter(D.name == "نوع الوقود").one()
        assert def_fuel.equipment_type_id == ids["type_id"]
        assert def_fuel.category_id == ids["cat_id"]
        assert len(value_rows(def_fuel.id)) == 1

        # د: المرفوض لا يُنشأ تعريفه أصلًا
        assert db.query(D).filter(D.name == "طول المركبة").first() is None
    finally:
        db.close()

    # 4. إعادة الإرسال: لا تعريفات ولا صفوف جديدة
    response2 = auth_client.post("/document-import/apply", json=json_data)
    assert response2.status_code == 200
    s2 = response2.json()["summary"]
    assert counts(TestingSession) == after_first
    assert s2["created_definition"] == 0
    assert s2["applied"] == 5  # أ + ب + ج + الاسمان المتطابقان للوقود
    assert s2["not_approved"] == 1
    assert s2["invalid_definition"] == 1


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

    assert result["summary"]["applied"] == 0
    assert result["results"][0]["definition_id"] == def2_id

    # القاعدة لم تتغير: القيمة الأصلية محفوظة
    db = TestingSession()
    try:
        row = db.query(EquipmentModelSpecValue).filter_by(
            equipment_model_id=model_id, spec_definition_id=def2_id).one()
        assert row.value == "5000"
    finally:
        db.close()


def test_html_form_roundtrip(client_and_model_data):
    """مسار المتصفح الحقيقي: POST بـ data= (نموذج HTML) بحقول candidates-N-*."""
    auth_client, ids, S = client_and_model_data
    def_id = make_def(S, "قدرة المحرك FORM", "kW", ids["type_id"], data_type="number")
    form = {
        "model_id": str(ids["model_id"]),
        # 0: تعريف موجود، عدّل المستخدم القيمة من 150 إلى 999
        "candidates-0-definition_id": str(def_id), "candidates-0-name_found": "قدرة المحرك FORM",
        "candidates-0-value": "999", "candidates-0-unit": "kW", "candidates-0-is_new": "false",
        "candidates-0-approved": "true",
        "candidates-0-value_original": "150", "candidates-0-unit_original": "kW",
        # 1: خاصية جديدة معتمدة
        "candidates-1-definition_id": "", "candidates-1-name_found": "عدد المقاعد FORM",
        "candidates-1-value": "20", "candidates-1-unit": "", "candidates-1-is_new": "true",
        "candidates-1-approved": "true",
        "candidates-1-value_original": "20", "candidates-1-unit_original": "",
        # 2: غير معتمدة (خانة approved غائبة كما يفعل المتصفح)
        "candidates-2-definition_id": "", "candidates-2-name_found": "مرفوضة FORM",
        "candidates-2-value": "1", "candidates-2-unit": "", "candidates-2-is_new": "true",
        "candidates-2-value_original": "1", "candidates-2-unit_original": "",
    }
    d0, _ = counts(S)
    r = auth_client.post("/document-import/apply", data=form)
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "عدد المقاعد FORM" in r.text and "مرفوضة FORM" in r.text
    assert "✓ تعريف جديد" in r.text and "✗ غير معتمد" in r.text

    db = S()
    try:
        row = db.query(EquipmentModelSpecValue).filter_by(
            equipment_model_id=ids["model_id"], spec_definition_id=def_id).one()
        assert row.value == "999"  # القيمة المعدّلة لا الأصلية
        seats = db.query(EquipmentModelSpecDefinition).filter_by(name="عدد المقاعد FORM").one()
        assert seats.equipment_type_id == ids["type_id"] and seats.category_id == ids["cat_id"]
        assert db.query(EquipmentModelSpecDefinition).filter_by(name="مرفوضة FORM").count() == 0
    finally:
        db.close()
    assert counts(S)[0] == d0 + 1  # تعريف جديد واحد فقط


def test_new_definition_is_listed_in_library(client_and_model_data):
    """التعريف المنشأ يظهر في قائمة المكتبة بالمجموعة الافتراضية والنوع والفئة."""
    from app.modules.equipment_types.services import list_spec_definitions
    auth_client, ids, S = client_and_model_data
    r = apply_json(auth_client, ids["model_id"], [cand("خاصية مكتبة LIB", "3", "kg", is_new=True)])
    assert r.json()["results"][0]["status"] == "created_definition"
    db = S()
    try:
        found = [d for d in list_spec_definitions(db) if d.name == "خاصية مكتبة LIB"]
        assert len(found) == 1
        d = found[0]
        assert d.group_name == "التعريف الفني"
        assert d.equipment_type_id == ids["type_id"] and d.category_id == ids["cat_id"]
        assert d.unit == "kg" and d.data_type == "text"
    finally:
        db.close()


def test_out_of_scope_definition(client_and_model_data):
    """تعريف تابع لنوع معدة آخر لا يُربط ولا يُنشأ بدله شيء (بالاسم وبالمعرف)."""
    auth_client, ids, S = client_and_model_data
    other_type = make_type(S, "نوع آخر OTHER", ids["cat_id"])
    other_def = make_def(S, "خاصية نوع آخر OTHER", "kg", other_type)
    before = counts(S)
    res = apply_json(auth_client, ids["model_id"], [
        cand("خاصية نوع آخر OTHER", "5", "kg", is_new=True),
        cand("خاصية نوع آخر OTHER", "5", "kg", definition_id=other_def),
    ]).json()
    assert [x["status"] for x in res["results"]] == ["definition_out_of_scope"] * 2
    assert res["summary"]["definition_out_of_scope"] == 2 and res["summary"]["applied"] == 0
    assert counts(S) == before


def test_batch_partial(client_and_model_data):
    """العنصر غير الصالح لا يُلغي بقية الدفعة."""
    auth_client, ids, S = client_and_model_data
    ok_id = make_def(S, "صالحة BATCH", "kg", ids["type_id"])
    res = apply_json(auth_client, ids["model_id"], [
        cand("صالحة BATCH", "7", "kg", definition_id=ok_id),
        cand("وهمية BATCH", "1", "kg", definition_id=99999),
    ]).json()
    assert [x["status"] for x in res["results"]] == ["applied", "invalid_definition"]
    db = S()
    try:
        row = db.query(EquipmentModelSpecValue).filter_by(
            equipment_model_id=ids["model_id"], spec_definition_id=ok_id).one()
        assert row.value == "7"
    finally:
        db.close()


def test_rollback_on_unexpected_error(client_and_model_data, monkeypatch):
    """استثناء غير متوقع عند العنصر الثاني يلغي الدفعة كلها (لا تعريفات ولا قيم) ويُرجع 500."""
    from app.modules.document_import import services
    auth_client, ids, S = client_and_model_data
    n = {"i": 0}
    real = services.create_spec_definition

    def boom(*a, **k):
        n["i"] += 1
        if n["i"] == 2:
            raise RuntimeError("boom")
        return real(*a, **k)

    monkeypatch.setattr(services, "create_spec_definition", boom)
    before = counts(S)
    r = apply_json(auth_client, ids["model_id"], [
        cand("جديدة ROLL 1", "1", is_new=True),
        cand("جديدة ROLL 2", "2", is_new=True),
    ])
    assert r.status_code == 500
    assert counts(S) == before
    db = S()
    try:
        names = [d.name for d in db.query(EquipmentModelSpecDefinition).filter(
            EquipmentModelSpecDefinition.name.in_(["جديدة ROLL 1", "جديدة ROLL 2"])).all()]
        assert names == []
    finally:
        db.close()


def test_definition_error_does_not_cancel_batch(client_and_model_data, monkeypatch):
    """ValueError من create_spec_definition ← definition_error لذلك العنصر فقط."""
    from app.modules.document_import import services
    auth_client, ids, S = client_and_model_data
    real = services.create_spec_definition

    def maybe_fail(db, data, *a, **k):
        if data.name == "خاصية فاشلة DEFERR":
            raise ValueError("توجد خاصية بهذا الاسم مسبقًا")
        return real(db, data, *a, **k)

    monkeypatch.setattr(services, "create_spec_definition", maybe_fail)
    res = apply_json(auth_client, ids["model_id"], [
        cand("خاصية فاشلة DEFERR", "1", is_new=True),
        cand("خاصية سليمة DEFERR", "2", is_new=True),
    ]).json()
    assert [x["status"] for x in res["results"]] == ["definition_error", "created_definition"]
    assert res["results"][0]["reason"] == "توجد خاصية بهذا الاسم مسبقًا"


def test_invalid_value_empty(client_and_model_data):
    auth_client, ids, S = client_and_model_data
    did = make_def(S, "فارغة EMPTY", "kg", ids["type_id"])
    before = counts(S)
    res = apply_json(auth_client, ids["model_id"], [cand("فارغة EMPTY", "  ", "kg", definition_id=did)]).json()
    assert res["results"][0]["status"] == "invalid_value"
    assert res["results"][0]["reason"] == "empty_value"
    assert counts(S) == before


def test_value_validation_by_data_type(client_and_model_data):
    """نفس قواعد الإدخال اليدوي: رقم للنوع number، وإحدى الخيارات للنوع select."""
    auth_client, ids, S = client_and_model_data
    num_id = make_def(S, "عددية NUMV", "kg", ids["type_id"], data_type="number")
    sel_id = make_def(S, "اختيارية SELV", None, ids["type_id"], data_type="select", options="أ,ب")
    res = apply_json(auth_client, ids["model_id"], [
        cand("عددية NUMV", "abc", "kg", definition_id=num_id),
        cand("عددية NUMV", "12.5", "kg", definition_id=num_id),
        cand("اختيارية SELV", "ج", definition_id=sel_id),
        cand("اختيارية SELV", "أ", definition_id=sel_id),
    ]).json()
    assert [x["status"] for x in res["results"]] == ["invalid_value", "applied", "invalid_value", "applied"]
    assert [x["reason"] for x in res["results"]][0::2] == ["not_a_number", "not_in_options"]


def test_unit_cases(client_and_model_data):
    auth_client, ids, S = client_and_model_data
    a = make_def(S, "وحدة أ UNIT", "kg", ids["type_id"])
    b = make_def(S, "وحدة ب UNIT", "kg", ids["type_id"])
    c_ = make_def(S, "وحدة ج UNIT", "kg", ids["type_id"])
    res = apply_json(auth_client, ids["model_id"], [
        cand("وحدة أ UNIT", "1", " KG ", definition_id=a),   # يختلف بالحالة والمسافات فقط ← applied
        cand("وحدة ب UNIT", "2", "", definition_id=b),        # وحدة فارغة ← applied
        cand("وحدة ج UNIT", "3", "t", definition_id=c_),      # وحدة مختلفة ← unit_mismatch
        cand("وحدة أ UNIT", "1", "t", is_new=True),           # is_new بتعريف موجود ووحدة مختلفة ← unit_mismatch
    ]).json()
    assert [x["status"] for x in res["results"]] == ["applied", "applied", "unit_mismatch", "unit_mismatch"]
    assert res["summary"]["applied"] == 2 and res["summary"]["unit_mismatch"] == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
