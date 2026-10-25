"""شروط استحقاق عمليات الصيانة بحسب الطراز.

المرجع المعماري: العملية الفنية (`MaintenanceOperation`) تعريف مشترك، وشرط
الاستحقاق وإعداد الإنذار يخصّان علاقة العملية بالطراز
(`maintenance_operation_models`). هذا الملف يحرس:

* استقلال شروط الطرازات وعدم تأثر أحدها بتعديل الآخر؛
* عرض عمودي «الشرط» و«الإنذار» (قيمة مباشرة / مشتركة / شروط متعددة / غير محدد / بلا طرازات)؛
* استخدام محرك الاستحقاق شرط الطراز الصحيح لا القيمة القديمة على العملية؛
* بقاء شروط الخطة مستقلة عن شروط العملية؛
* عمل الإضافة والتعديل والحذف عبر الـAPI؛
* ترحيل الأعمدة الجديدة دون فقدان صفوف العلاقة.
"""

import re
from io import BytesIO
from html import unescape
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook, load_workbook
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.dependencies import get_current_user
from app.database.base import Base
from app.database import session as session_module
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentModel, EquipmentType
from app.modules.maintenance.models import MaintenanceOperation, MaintenancePlan, MaintenanceRecord, maintenance_operation_models
from app.modules.maintenance.router import router as maintenance_router
from app.modules.maintenance.services import (
    CONDITION_MODEL,
    CONDITION_UNSET,
    MULTIPLE_CONDITIONS_LABEL,
    MULTIPLE_WARNINGS_LABEL,
    CONDITION_UNSET_LABEL,
    CONDITION_NO_INTERVAL_LABEL,
    ModelCondition,
    condition_axis_text,
    condition_unit_text,
    effective_operations_for_equipment,
    meter_required_for_condition,
    operation_condition_for_model,
    summarize_operation_conditions,
    validate_operation_applicable_to_equipment,
    warning_setting_text,
)
from app.modules.maintenance.models import MaintenanceOperation
from app.modules.maintenance.operation_excel_import import (
    GENERAL_OPERATION_IMPORT_HEADERS,
    OPERATION_IMPORT_HEADERS,
    parse_general_operation_workbook,
    parse_operation_workbook,
)
from app.modules.users.models import User

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Session = sessionmaker(bind=engine, expire_on_commit=False)
# اسم مقروء لمصنع الجلسات يستخدمه ملف اختبارات واجهة المكتبة أيضًا.
TestSession = Session


def _link(db, operation, model, **condition):
    """Relation row = the eligibility condition of one model for one operation."""
    db.execute(
        maintenance_operation_models.insert().values(
            operation_id=operation.id,
            equipment_model_id=model.id,
            condition_source=CONDITION_MODEL,
            **condition,
        )
    )


@pytest.fixture()
def api():
    """واجهة REST الحقيقية على قاعدة مؤقتة معزولة (لا تُقرأ fleet_assets.db)."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    seed = Session()
    equipment_type = EquipmentType(name="نوع اختبار شروط الطراز", measurement_unit="km")
    seed.add(equipment_type)
    seed.flush()
    model_a = EquipmentModel(name="طراز ألف", equipment_type_id=equipment_type.id)
    model_b = EquipmentModel(name="طراز باء", equipment_type_id=equipment_type.id)
    seed.add_all([model_a, model_b])
    seed.flush()
    equipment_a = Equipment(
        asset_code="MODEL-COND-A",
        registration_number="MODEL-COND-A",
        equipment_type_id=equipment_type.id,
        equipment_model_id=model_a.id,
    )
    seed.add(equipment_a)
    seed.add(User(id=1, username="model-cond-admin", full_name="مسؤول", hashed_password="x", role="admin", is_active=True))
    seed.commit()
    ids = {
        "equipment_type": equipment_type.id,
        "model_a": model_a.id,
        "model_b": model_b.id,
        "equipment_a": equipment_a.id,
    }
    seed.close()

    app = FastAPI()
    app.include_router(maintenance_router)

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    def override_user():
        # كائن مستخدم مكتمل المفتاح يكفي: الـAPI يقرأ id فقط لتسجيل المنفّذ.
        return User(id=1, username="model-cond-admin", full_name="مسؤول", hashed_password="x", role="admin", is_active=True)

    app.dependency_overrides[session_module.get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    with TestClient(app) as client:
        yield client, ids


def _condition(model_id, intervals=None, source=CONDITION_MODEL, **warnings):
    values = {"condition_source": source, "equipment_model_id": model_id}
    values.update(intervals or {})
    # Note: warnings are now at the operation level, not per-model
    return ModelCondition(**values)


def _test_app():
    app = FastAPI()
    app.include_router(maintenance_router)

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    def override_user():
        # كائن مستخدم مكتمل المفتاح يكفي: الـAPI يقرأ id فقط لتسجيل المنفّذ.
        return User(id=1, username="model-cond-admin", full_name="مسؤول", hashed_password="x", role="admin", is_active=True)

    app.dependency_overrides[session_module.get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    return app


# --------------------------------------------------------- صفحة مكتبة الشروط


def test_rules_page_renders_and_distinguishes_loading_empty_and_error_states(api):
    """الصفحة تُبنى من الـAPI الصحيح، وتفرّق بين التحميل والنجاح الفارغ والخطأ."""
    client, _ = api
    response = client.get("/maintenance/rules")
    assert response.status_code == 200, response.text
    page = response.text

    # أساسيات الصفحة: الجدول وأعمدة الإنذار والحالة ونموذج الإدخال.
    assert 'id="operationsTable"' in page
    assert 'data-filter-col="warning"' in page
    # صفحة العمليات تعرض الشرط وتتيح الانتقال إلى مكتبة أي طراز.
    assert 'data-filter-col="condition"' in page
    assert 'id="libraryModelFilter"' in page
    assert 'id="conditionDetailsBody"' not in page
    assert 'id="editorModelsBody"' not in page
    assert 'id="operationImportDialog"' in page
    assert 'id="downloadOperationTemplate"' in page
    assert all(f"<th scope=\"col\">{header}</th>" in page for header in OPERATION_IMPORT_HEADERS)

    # مصدر البيانات: واجهات المكتبة الحقيقية.
    assert "const api='/api/maintenance'" in page
    assert "${api}/operations`" in page
    assert "${api}/model-operations?equipment_model_id=" in page

    # لا يستخدم القالب حقلًا غير موجود في الصفحة (كان يُسقط التحميل سابقًا).
    assert "$('operationModels')" not in page
    assert "getElementById('operationModels')" not in page

    # حالات الجدول الثلاث متميزة: جارٍ التحميل / نجاح فارغ / خطأ.
    assert "جارٍ تحميل المكتبة" in page
    assert "لا توجد عمليات مطابقة" in page
    assert "خطأ في التحميل" in page
    assert "state.loadState=state.hasLoadedOperations?'ready':'error'" in page

    # مكتبة الطراز تعرض عملياتها الخاصة وشرطها المحفوظ لكل عملية.
    assert "scope_model_id" not in page
    assert "model_operation_id" in page
    assert "conditionDetails" not in page


def test_rules_page_lists_every_operation_with_its_model_summary(api):
    """الصفحة تُحمّل من /api/maintenance/operations بلا خلل تحميل."""
    client, ids = api
    client.post(
        "/api/maintenance/operations",
        json=_operation_payload(
            "عملية ظاهرة في الصفحة",
            [{"model_id": ids["model_a"], "interval_km": 5000}],
            warning_km=500,  # Unified warning at operation level
        ),
    )
    page = client.get("/maintenance/rules")
    assert page.status_code == 200
    operations = client.get("/api/maintenance/operations")
    assert operations.status_code == 200
    names = [item["name"] for item in operations.json()]
    assert "عملية ظاهرة في الصفحة" in names


def test_scoped_library_excel_import_and_general_library_remain_separate(api):
    """Real HTTP workbook upload creates private model operations without changing the general plan library."""
    client, ids = api
    # The template is equipment-neutral; model selection applies only to the upload destination.
    template_response = client.get("/maintenance/rules/operation-template.xlsx")
    assert template_response.status_code == 200, template_response.text
    assert template_response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert 'maintenance_operations_template.xlsx' in template_response.headers["content-disposition"]

    workbook = load_workbook(BytesIO(template_response.content))
    assert "العمليات" in workbook.sheetnames
    assert "إرشادات" in workbook.sheetnames
    sheet = workbook["العمليات"]
    assert tuple(cell.value for cell in sheet[1]) == OPERATION_IMPORT_HEADERS
    assert OPERATION_IMPORT_HEADERS.index("قيمة الشرط 1") < OPERATION_IMPORT_HEADERS.index("قيمة الإنذار 1")
    assert "قالب عام" in workbook["إرشادات"]["A2"].value
    assert "الطراز المستهدف" in workbook["إرشادات"]["A2"].value
    assert "مكتبة الطراز:" not in "\n".join(
        str(cell.value or "") for row in workbook["إرشادات"].iter_rows() for cell in row
    )
    unit_validations = [validation for validation in sheet.data_validations.dataValidation if validation.type == "list"]
    assert len(unit_validations) == 2
    assert all(validation.errorStyle == "stop" for validation in unit_validations)
    unit_validation = next(validation for validation in unit_validations if validation.formula1 == "=MaintenanceUnitOptions")
    assert all(f"{column}2:{column}2001" in str(unit_validation.sqref) for column in ("E", "G", "I", "K", "M", "O"))
    assert [workbook["القوائم"].cell(row, 2).value for row in range(1, 4)] == ["كم", "ساعة تشغيل", "يوم"]
    sheet.append((
        "تبديل مرشح الهواء", "عملية خاصة بميكرا", "بدون مجموعة",
        20000, "كم", 180, "يوم", None, None,
        500, "كم", 12.5, "ساعة تشغيل", None, None,
    ))
    stream = BytesIO()
    workbook.save(stream)
    workbook.close()

    upload = client.post(
        "/maintenance/rules/import",
        data={"model_id": str(ids["model_a"])},
        files={"file": ("micra-operations.xlsx", stream.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        follow_redirects=False,
    )
    assert upload.status_code == 303
    assert f"model_id={ids['model_a']}" in upload.headers["location"]
    assert "imported=1" in upload.headers["location"]

    imported_page = client.get(upload.headers["location"])
    assert imported_page.status_code == 200
    assert re.search(rf'<option value="{ids["model_a"]}"[^>]*\bselected(?:\s|>)', imported_page.text)
    assert 'id="libraryModelFilter"' in imported_page.text
    assert 'id="modelConditionEditor"' in imported_page.text

    imported = client.get(f"/api/maintenance/model-operations?equipment_model_id={ids['model_a']}")
    assert imported.status_code == 200
    private_operation = next(item for item in imported.json() if item["name"] == "تبديل مرشح الهواء")
    assert private_operation["equipment_model_id"] == ids["model_a"]
    assert float(private_operation["interval_km"]) == 20000
    assert private_operation["interval_days"] == 180
    assert float(private_operation["warning_km"]) == 500
    assert float(private_operation["warning_hours"]) == 12.5

    # A different model cannot see this model-scoped operation.
    other_model = client.get(f"/api/maintenance/model-operations?equipment_model_id={ids['model_b']}")
    assert all(item["name"] != "تبديل مرشح الهواء" for item in other_model.json())

    # Reuse the same generic workbook structure for a different equipment model.
    workbook_for_other_model = load_workbook(BytesIO(stream.getvalue()))
    workbook_for_other_model["العمليات"]["A2"] = "فحص مضخة الوقود"
    workbook_for_other_model["العمليات"]["B2"] = "عملية خاصة بطراز آخر"
    other_model_stream = BytesIO()
    workbook_for_other_model.save(other_model_stream)
    workbook_for_other_model.close()
    second_upload = client.post(
        "/maintenance/rules/import",
        data={"model_id": str(ids["model_b"])},
        files={"file": ("generic-operations.xlsx", other_model_stream.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        follow_redirects=False,
    )
    assert second_upload.status_code == 303
    assert f"model_id={ids['model_b']}" in second_upload.headers["location"]
    assert "imported=1" in second_upload.headers["location"]
    other_model_after_import = client.get(
        f"/api/maintenance/model-operations?equipment_model_id={ids['model_b']}"
    ).json()
    assert any(item["name"] == "فحص مضخة الوقود" for item in other_model_after_import)
    assert all(item["name"] != "فحص مضخة الوقود" for item in imported.json())

    # The old plan flow still reads only the reusable public library.
    public_create = client.post(
        "/api/maintenance/operations",
        json={"name": "عملية عامة للخطة", "warning_km": 0},
    )
    assert public_create.status_code == 201, public_create.text
    public_names = {item["name"] for item in client.get("/api/maintenance/operations").json()}
    assert "عملية عامة للخطة" in public_names
    assert "تبديل مرشح الهواء" not in public_names
    assert "تبديل مرشح الهواء" not in {
        item["name"] for item in client.get("/api/maintenance/model-operations?equipment_model_id=" + str(ids["model_b"])).json()
    }

    # A second upload with a duplicate scoped name is rejected atomically.
    duplicate = client.post(
        "/maintenance/rules/import",
        data={"model_id": str(ids["model_a"])},
        files={"file": ("micra-operations.xlsx", stream.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        follow_redirects=False,
    )
    assert duplicate.status_code == 303
    assert "import_error=" in duplicate.headers["location"]
    after_duplicate = client.get(f"/api/maintenance/model-operations?equipment_model_id={ids['model_a']}").json()
    assert sum(item["name"] == "تبديل مرشح الهواء" for item in after_duplicate) == 1


def test_general_library_excel_template_and_upload_create_public_operations_only(api):
    client, ids = api
    group_response = client.post(
        "/api/maintenance/operation-groups",
        json={"name": "مجموعة عامة للاختبار", "sort_order": 2},
    )
    assert group_response.status_code == 201, group_response.text
    group = group_response.json()

    template_response = client.get("/maintenance/rules/general-operation-template.xlsx")
    assert template_response.status_code == 200, template_response.text
    assert template_response.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert 'maintenance_general_operations_template.xlsx' in template_response.headers["content-disposition"]

    workbook = load_workbook(BytesIO(template_response.content))
    sheet = workbook["العمليات"]
    assert tuple(cell.value for cell in sheet[1]) == GENERAL_OPERATION_IMPORT_HEADERS
    assert not any("شرط" in str(cell.value) for cell in sheet[1])
    validations = [item for item in sheet.data_validations.dataValidation if item.type == "list"]
    assert {item.formula1 for item in validations} == {
        "=MaintenanceGroupOptions",
    }
    assert all("الحالة" not in str(cell.value or "") for cell in sheet[1])
    sheet.append(("تغيير زيت المحرك", "وصف العملية العامة", group["name"], 0, None, None))
    sheet.append(("فحص مضخة الوقود", "عملية عامة ثانية", "بدون مجموعة", None, 15.5, 0))
    stream = BytesIO()
    workbook.save(stream)
    workbook.close()

    upload = client.post(
        "/maintenance/rules/import-general",
        files={"file": ("general-operations.xlsx", stream.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        follow_redirects=False,
    )
    assert upload.status_code == 303
    assert "imported_general=2" in upload.headers["location"]
    assert "model_id=" not in upload.headers["location"]
    success_page = client.get(upload.headers["location"])
    assert success_page.status_code == 200
    assert "تم استيراد 2 عملية إلى مكتبة العمليات العامة." in success_page.text

    public_operations = client.get("/api/maintenance/operations").json()
    by_name = {operation["name"]: operation for operation in public_operations}
    active_operation = by_name["تغيير زيت المحرك"]
    second_operation = by_name["فحص مضخة الوقود"]
    assert active_operation["description"] == "وصف العملية العامة"
    assert active_operation["group_id"] == group["id"]
    assert float(active_operation["warning_km"]) == 0
    assert active_operation["is_active"] is True
    assert active_operation["condition_source"] == "none"
    assert active_operation["model_conditions"] == []
    assert float(second_operation["warning_hours"]) == 15.5
    assert second_operation["warning_days"] == 0
    assert second_operation["is_active"] is True

    private_a = client.get(f"/api/maintenance/model-operations?equipment_model_id={ids['model_a']}").json()
    assert all(operation["name"] not in {"تغيير زيت المحرك", "فحص مضخة الوقود"} for operation in private_a)

    duplicate = client.post(
        "/maintenance/rules/import-general",
        files={"file": ("general-operations.xlsx", stream.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        follow_redirects=False,
    )
    assert duplicate.status_code == 303
    assert "import_error=" in duplicate.headers["location"]
    after_duplicate = client.get("/api/maintenance/operations").json()
    assert sum(operation["name"] == "تغيير زيت المحرك" for operation in after_duplicate) == 1
    assert sum(operation["name"] == "فحص مضخة الوقود" for operation in after_duplicate) == 1


def test_general_excel_import_server_validation_rejects_negative_alarm_values():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "العمليات"
    sheet.append(GENERAL_OPERATION_IMPORT_HEADERS)
    sheet.append(("عملية إنذار سالب", "", "بدون مجموعة", -1, None, None))
    stream = BytesIO()
    workbook.save(stream)
    workbook.close()

    with pytest.raises(ValueError, match="لا تقل قيمة «إنذار كم» عن صفر"):
        parse_general_operation_workbook(stream.getvalue(), [])


def test_excel_import_accepts_multiple_conditions_and_warning_axes():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "العمليات"
    sheet.append(OPERATION_IMPORT_HEADERS)
    sheet.append((
        "فحص مضخة الوقود", "", "بدون مجموعة",
        250, "ساعة تشغيل", 90, "يوم", None, None,
        500, "كم", 12.5, "ساعة تشغيل", 3, "يوم",
    ))
    stream = BytesIO()
    workbook.save(stream)
    workbook.close()

    rows = parse_operation_workbook(stream.getvalue(), [])
    assert rows[0]["condition"]["interval_hours"] == Decimal("250")
    assert rows[0]["condition"]["interval_days"] == 90
    assert rows[0]["warning_km"] == Decimal("500")
    assert rows[0]["warning_hours"] == Decimal("12.5")
    assert rows[0]["warning_days"] == 3


def test_excel_import_rejects_invalid_or_duplicate_units_and_unpaired_values():
    valid_row = [
        "عملية اختبار", "", "بدون مجموعة",
        10000, "كم", None, None, None, None,
        500, "كم", None, None, None, None,
    ]
    invalid_rows = [
        ("وحدة «الشرط» غير صالحة", {4: "كيلومتر"}),
        ("لا تكرر وحدة «كم» ضمن الشرط", {5: 30, 6: "كم"}),
        ("قيمة الشرط ووحدتها معًا", {3: None}),
        ("قيمة الإنذار ووحدتها معًا", {9: None}),
    ]

    for message, changes in invalid_rows:
        row = valid_row.copy()
        for index, value in changes.items():
            row[index] = value
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "العمليات"
        sheet.append(OPERATION_IMPORT_HEADERS)
        sheet.append(row)
        stream = BytesIO()
        workbook.save(stream)
        workbook.close()
        with pytest.raises(ValueError, match=message):
            parse_operation_workbook(stream.getvalue(), [])


def test_excel_import_requires_at_least_one_warning_value():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "العمليات"
    sheet.append(OPERATION_IMPORT_HEADERS)
    sheet.append((
        "فحص مضخة الوقود", "", "بدون مجموعة",
        250, "ساعة تشغيل", None, None, None, None,
        None, None, None, None, None, None,
    ))
    stream = BytesIO()
    workbook.save(stream)
    workbook.close()

    with pytest.raises(ValueError, match="قيمة الإنذار واحدة على الأقل"):
        parse_operation_workbook(stream.getvalue(), [])


def test_model_library_create_edit_toggle_and_delete_are_scoped(api):
    client, ids = api
    missing_warning = client.post(
        "/api/maintenance/model-operations",
        json={
            "name": "عملية بلا إنذار",
            "equipment_model_id": ids["model_a"],
            "interval_hours": 250,
        },
    )
    assert missing_warning.status_code == 422
    assert "إنذار واحدة على الأقل" in missing_warning.text

    payload = {
        "name": "تغيير سائل التبريد",
        "equipment_model_id": ids["model_a"],
        "interval_hours": 250,
        "warning_days": 30,
        "warning_hours": 12.5,
    }
    created = client.post("/api/maintenance/model-operations", json=payload)
    assert created.status_code == 201, created.text
    operation = created.json()
    assert operation["equipment_model_id"] == ids["model_a"]
    assert float(operation["interval_hours"]) == 250
    assert float(operation["warning_hours"]) == 12.5

    cleared_warnings = client.put(
        f"/api/maintenance/model-operations/{operation['id']}",
        json={
            "name": operation["name"],
            "interval_hours": 250,
            "warning_km": None,
            "warning_hours": None,
            "warning_days": None,
        },
    )
    assert cleared_warnings.status_code == 422

    page = client.get(f"/maintenance/rules?view_model_id={ids['model_a']}")
    assert page.status_code == 200
    assert re.search(rf'<option value="{ids["model_a"]}"[^>]*\bselected(?:\s|>)', page.text)

    updated_payload = {
        "name": "تغيير سائل التبريد وتفقده",
        "description": "تعديل خاص بالطراز المحدد",
        "group_id": None,
        "warning_km": None,
        "warning_hours": 20,
        "warning_days": 20,
        "is_active": False,
        "interval_km": None,
        "interval_hours": None,
        "interval_days": 180,
    }
    updated = client.put(f"/api/maintenance/model-operations/{operation['id']}", json=updated_payload)
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "تغيير سائل التبريد وتفقده"
    assert updated.json()["is_active"] is False
    assert updated.json()["interval_days"] == 180
    assert float(updated.json()["warning_hours"]) == 20

    activated = client.put(
        f"/api/maintenance/model-operations/{operation['id']}",
        json={**updated_payload, "is_active": True},
    )
    assert activated.status_code == 200
    assert activated.json()["is_active"] is True
    assert client.delete(f"/api/maintenance/model-operations/{operation['id']}").status_code == 204
    assert all(
        item["name"] != "تغيير سائل التبريد وتفقده"
        for item in client.get(f"/api/maintenance/model-operations?equipment_model_id={ids['model_a']}").json()
    )


def test_operating_hours_warning_reaches_the_maintenance_notification_provider(api):
    client, ids = api
    db = Session()
    try:
        equipment = db.get(Equipment, ids["equipment_a"])
        equipment.equipment_type.measurement_unit = "hours"
        db.commit()
    finally:
        db.close()

    created = client.post(
        "/api/maintenance/model-operations",
        json={
            "name": "إنذار ساعات التشغيل",
            "equipment_model_id": ids["model_a"],
            "interval_hours": 500,
            "warning_hours": 25,
        },
    )
    assert created.status_code == 201, created.text
    execution = client.post(
        "/api/maintenance/execution",
        json={
            "equipment_id": ids["equipment_a"],
            "model_operation_id": created.json()["id"],
            "maintenance_date": str(date.today() - timedelta(days=1)),
            "meter_value": 1000,
        },
    )
    assert execution.status_code == 201, execution.text

    from app.modules.meter_readings.services import create_reading

    db = Session()
    try:
        create_reading(
            db,
            ids["equipment_a"],
            hours=1475,
            reading_date=datetime.now(),
        )
    finally:
        db.close()

    from app.modules.maintenance.services import (
        condition_for_equipment,
        current_meter_value,
        effective_operations_for_equipment,
        latest_readings,
        latest_records,
        operation_condition_meta,
        operation_reference,
    )
    from app.modules.notifications.providers import maintenance_due_provider

    db = Session()
    try:
        equipment = db.get(Equipment, ids["equipment_a"])
        assert equipment.equipment_type.measurement_unit == "hours"
        assert equipment.current_hours == Decimal("1475")
        operations = effective_operations_for_equipment(db, equipment)
        operation = next(item for item in operations if item.id == created.json()["id"])
        assert operation.interval_hours == Decimal("500.0")
        assert operation.warning_hours == Decimal("25.0")
        records = latest_records(db)
        record = records.get((equipment.id, *operation_reference(operation)))
        assert record is not None
        assert record.meter_value == Decimal("1000.0")
        current_value = current_meter_value(equipment, latest_readings(db).get(equipment.id))
        assert current_value == Decimal("1475")
        state, css, _, _ = operation_condition_meta(
            operation,
            condition_for_equipment(db, operation, equipment),
            equipment,
            record,
            current_value,
        )
        assert state == "تقترب"
        assert css == "warning"
        note = next(
            item for item in maintenance_due_provider(db)
            if item["title"].startswith("إنذار ساعات التشغيل")
        )
    finally:
        db.close()
    assert note["severity"] == "upcoming"
    assert "تقترب" in note["detail"]


def test_plans_page_carries_the_model_condition_from_the_service(api):
    """صفحة الخطط تعرض شرط الطراز المحفوظ، و«الشرط غير محدد» عندما لا يوجد شرط."""
    client, ids = api
    created = client.post(
        "/api/maintenance/operations",
        json=_operation_payload(
            "عملية الخطط",
            [
                {"model_id": ids["model_a"], "interval_km": 10000},
                {"model_id": ids["model_b"], "condition_source": "unset"},
            ],
            warning_km=1000,  # Unified warning at operation level
        ),
    ).json()
    page = client.get("/maintenance/plans")
    assert page.status_code == 200, page.text
    body = page.text
    # الخريطة تأتي من الخدمة وتحمل شرط كل (عملية، طراز)، مع تمييز غير المحدد.
    assert "operationConditions=" in body
    assert f'"{created["id"]}:{ids["model_a"]}"' in body
    assert f'"{created["id"]}:{ids["model_b"]}"' in body
    assert '"is_defined": true' in body
    assert '"is_defined": false' in body
    # شروط العمليات الخاصة تظهر في المكتبة المختارة؛ شرط الخطة يبقى المرجع عند التنفيذ.
    assert "o.source==='model'" in body
    # ونص «غير محدد» يُبنى في العميل من نفس الخريطة.
    assert "الشرط غير محدد لهذا الطراز" in body


def test_records_page_builds_meter_requirement_from_the_model_condition(api):
    """حاجة العداد في نموذج السجل تُبنى من شرط الطراز، لا من القيمة القديمة على العملية."""
    client, ids = api
    created = client.post(
        "/api/maintenance/operations",
        json=_operation_payload(
            "عملية عدّاد الطراز",
            [
                {"model_id": ids["model_a"], "interval_km": 5000},
                {"model_id": ids["model_b"], "condition_source": "unset"},
            ],
        ),
    ).json()
    page = client.get("/maintenance/records")
    assert page.status_code == 200, page.text
    body = page.text
    assert "data-meter-models" in body
    assert "requiresMeterFor" in body
    # العتاد المسجّل يخص الطراز (أ): العداد مطلوب لشرطه، وغير مطلوب للطراز (ب) بلا شرط.
    assert f"{ids['model_a']}:1" in body, "طراز له شرط كيلومترات => العداد مطلوب"
    assert f"{ids['model_b']}:0" in body, "طراز بلا شرط محفوظ => العداد غير مطلوب"
    assert f"{ids['model_b']}:1" not in body
    # والقيمة القديمة على العملية لم تعد تُستخدم في هذا القرار.
    assert "o.interval_km is not none" not in body

    # ولا يمنع الخادم تسجيل التنفيذ لطراز شرطه محدد (القراءة مُمرَّرة هنا).
    response = client.post(
        "/api/maintenance/execution",
        json={
            "equipment_id": ids["equipment_a"],
            "operation_id": created["id"],
            "maintenance_date": str(date(2026, 9, 25)),
            "meter_value": 5000,
        },
    )
    assert response.status_code == 201, response.text


def test_meter_requirement_follows_the_axis_of_the_equipment_unit():
    """العداد مطلوب فقط إذا كان لشرط الطراز فاصل على محور وحدة العتاد."""
    km_condition = _condition(1, {"interval_km": Decimal("5000")})
    hours_condition = _condition(1, {"interval_hours": Decimal("250")})
    days_condition = _condition(1, {"interval_days": 30})
    unset_condition = _condition(1, source=CONDITION_UNSET)

    assert meter_required_for_condition(km_condition, "km") is True
    assert meter_required_for_condition(km_condition, "hours") is False
    assert meter_required_for_condition(hours_condition, "hours") is True
    assert meter_required_for_condition(hours_condition, "km") is False
    assert meter_required_for_condition(days_condition, "km") is False
    assert meter_required_for_condition(days_condition, "hours") is False
    assert meter_required_for_condition(unset_condition, "km") is False
    assert meter_required_for_condition(unset_condition, "hours") is False


# --------------------------------------------------------------- تفصيل الشروط


def test_condition_axes_and_unit_text_cover_the_three_supported_units():
    condition = _condition(
        1,
        {"interval_km": Decimal("5000"), "interval_hours": Decimal("250"), "interval_days": 90},
    )
    # Create a mock operation with warnings
    operation = MaintenanceOperation(
        warning_km=Decimal("500"), warning_hours=Decimal("25"), warning_days=30
    )
    assert condition_axis_text(condition) == "5000 كم أو 250 ساعة أو 90 يوم"
    assert condition_unit_text(condition) == "كم / ساعة / يوم"
    assert warning_setting_text(operation, condition) == "500 كم / 25 ساعة تشغيل / 30 يوم"


def test_condition_without_any_axis_is_reported_as_defined_but_empty():
    condition = _condition(1)
    operation = MaintenanceOperation()
    assert condition.is_defined is True
    assert condition.has_interval is False
    # كل حقول الفاصل فارغة ⇒ «غير محدد» بدلًا من «بدون فاصل محدد»، مع بقاء
    # حالة الشرط «معرّف» كما هي: لا تتحول إلى شرط مفعّل ولا يُستنتج فاصل.
    assert condition_axis_text(condition) == CONDITION_NO_INTERVAL_LABEL
    assert condition_axis_text(condition) == "غير محدد"
    assert condition_unit_text(condition) == "—"
    assert warning_setting_text(operation, condition) == "بدون إنذار مفعّل"


def test_unified_operation_warning_stays_visible_without_any_interval_axis():
    """إنذار العملية الموحد مستقل عن الفاصل: يظهر حتى مع شرط بلا أي فاصل."""
    condition = _condition(1)  # محفوظ بلا interval_km/hours/days
    operation = MaintenanceOperation(warning_km=Decimal("500"), warning_days=30)
    assert condition.is_defined is True
    assert condition.has_interval is False
    assert condition_axis_text(condition) == CONDITION_NO_INTERVAL_LABEL
    assert warning_setting_text(operation, condition) == "500 كم / 30 يوم"

    # الإنذار مستقل تمامًا: يظهر كذلك عند غياب أي علاقة بالطراز (condition=None).
    assert warning_setting_text(operation, None) == "500 كم / 30 يوم"


def test_unset_condition_is_never_rendered_as_a_value():
    condition = _condition(1, {"interval_km": Decimal("5000")}, source=CONDITION_UNSET)
    operation = MaintenanceOperation()
    assert condition.is_defined is False
    assert condition_axis_text(condition) == "—"
    # Unset conditions show "—" for warning, not the operation's warning
    assert warning_setting_text(operation, condition) == "—"
    
    # Even with operation-level warning, unset condition shows "—"
    operation_with_warning = MaintenanceOperation(warning_km=Decimal("500"))
    assert warning_setting_text(operation_with_warning, condition) == "—"
    
    # But for defined conditions, operation warning is shown
    defined_condition = _condition(1, {"interval_km": Decimal("5000")}, source=CONDITION_MODEL)
    assert warning_setting_text(operation_with_warning, defined_condition) == "500 كم"


# --------------------------------------------------------------- ملخص الجدول


def _detail(text, units, warning="—", defined=True):
    return {
        "is_defined": defined,
        "condition_text": text,
        "condition_units": units,
        "warning_text": warning,
    }


def test_summary_shows_the_single_model_condition_directly():
    summary = summarize_operation_conditions([_detail("5000 كم", ["km"])])
    assert summary["condition"] == "5000 كم"
    assert summary["condition_state"] == "shared"
    # Warning is now at operation level, not per-model
    assert summary["models_count"] == 1


def test_summary_shows_the_shared_condition_of_matching_models():
    summary = summarize_operation_conditions(
        [_detail("5000 كم", ["km"]), _detail("5000 كم", ["km"])]
    )
    assert summary["condition"] == "5000 كم"
    assert summary["has_multiple_conditions"] is False
    assert (summary["defined_count"], summary["models_count"]) == (2, 2)


def test_summary_reports_multiple_conditions_when_models_differ():
    summary = summarize_operation_conditions(
        [_detail("5000 كم", ["km"]), _detail("9000 كم", ["km"])]
    )
    assert summary["condition"] == MULTIPLE_CONDITIONS_LABEL
    assert summary["has_multiple_conditions"] is True
    assert summary["unit"] == "كم"


def test_summary_reports_unset_without_borrowing_another_model_value():
    summary = summarize_operation_conditions(
        [_detail("5000 كم", ["km"]), _detail("—", [], defined=False)]
    )
    assert summary["condition"] == CONDITION_UNSET_LABEL
    assert summary["condition_state"] == "partially_unset"
    assert summary["unset_count"] == 1


def test_summary_shows_no_condition_for_an_operation_without_models():
    summary = summarize_operation_conditions([])
    assert summary["condition"] is None
    assert summary["warning"] is None
    assert summary["unit"] is None
    assert summary["models_count"] == 0
    assert summary["condition_state"] == "no_models"


# --------------------------------------------------------- الانطباق والاستحقاق


def test_general_operation_without_model_produces_no_due_state_or_alert(monkeypatch):
    """عملية عامة في المكتبة بلا أي طراز: لا استحقاق ولا إنذار من قيمتها القديمة."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = Session()
    try:
        equipment_type = EquipmentType(name="نوع اختبار العملية العامة", measurement_unit="km")
        db.add(equipment_type)
        db.flush()
        model = EquipmentModel(name="طراز العملية العامة", equipment_type_id=equipment_type.id)
        db.add(model)
        db.flush()
        equipment = Equipment(
            asset_code="GENERAL-1",
            registration_number="GENERAL-1",
            equipment_type_id=equipment_type.id,
            equipment_model_id=model.id,
            current_odometer=Decimal("900000"),
        )
        # العملية تحمل قيمًا قديمة كبيرة، لكنها غير مرتبطة بأي طراز.
        general = MaintenanceOperation(
            name="عملية عامة بقيم قديمة",
            interval_km=Decimal("5000"),
            warning_km=Decimal("500"),
            is_active=True,
        )
        db.add_all([equipment, general])
        db.commit()

        # 1) لا تنطبق على العتاد، فلا تدخل في أي حساب استحقاق.
        assert effective_operations_for_equipment(db, equipment) == []
        assert validate_operation_applicable_to_equipment(db, general, equipment) is not None

        # 2) ولا يولّد مزوّد الإشعارات أي إنذار لها حتى بالعداد الحالي المتجاوز.
        from app.modules.notifications import providers

        monkeypatch.setattr(providers, "latest_readings", lambda session: {})
        monkeypatch.setattr(providers, "latest_records", lambda session: {})
        notes = providers.maintenance_due_provider(db)
        assert [note for note in notes if "عملية عامة بقيم قديمة" in note["title"]] == []

        # 3) ولا يُخفى الرقم القديم كأنه شرط: لا يوجد شرط محفوظ لأي طراز.
        assert operation_condition_for_model(db, general.id, model.id).is_defined is False
    finally:
        db.close()


def test_general_operation_is_absent_from_the_periodic_and_due_pages(api):
    """الصفحة الدورية وصفحة المستحقة لا تُظهران عملية غير مرتبطة بأي طراز."""
    client, ids = api
    client.post(
        "/api/maintenance/operations",
        json={"name": "عملية عامة لا تظهر", "equipment_model_conditions": [], "warning_km": 0},
    )
    assert client.post(
        "/api/maintenance/operations",
        json={
            "name": "عملية مرتبطة تظهر",
            "warning_km": 0,
            "equipment_model_conditions": [{"model_id": ids["model_a"], "interval_km": 5000}],
        },
    ).status_code == 201

    periodic = client.get("/maintenance/periodic").text
    due = client.get("/maintenance/due").text
    for page in (periodic, due):
        # العملية العامة لا تظهر في أي من الصفحتين التشغيليتين.
        assert "عملية عامة لا تظهر" not in page
    # وخيار تصفية «الشرط غير محدد» قائم في الصفحة الدورية للحالة المقابلة.
    assert CONDITION_UNSET_LABEL in periodic


def test_periodic_page_paginates_globally_and_keeps_summary_counts(api):
    client, ids = api
    db = Session()
    try:
        operations = [
            MaintenanceOperation(name=f"عملية ترقيم {index:03d}", is_active=True)
            for index in range(205)
        ]
        db.add_all(operations)
        db.flush()
        for operation in operations:
            _link(
                db,
                operation,
                db.get(EquipmentModel, ids["model_a"]),
                interval_km=5000,
            )
        db.commit()
    finally:
        db.close()

    first = client.get("/maintenance/periodic")
    assert first.status_code == 200
    assert first.text.count('data-status="') == 100
    assert "205" in first.text
    next_link = re.search(r'<a class="m-btn" href="([^"]+)">التالي</a>', first.text)
    assert next_link is not None

    second = client.get(unescape(next_link.group(1)))
    assert second.status_code == 200
    assert second.text.count('data-status="') == 100
    assert "عملية ترقيم 000" not in second.text
    assert "عملية ترقيم 100" in second.text
    previous_link = re.search(r'<a class="m-btn" href="([^"]+)">السابق</a>', second.text)
    assert previous_link is not None
    final_link = re.search(r'<a class="m-btn" href="([^"]+)">التالي</a>', second.text)
    assert final_link is not None

    final_page = client.get(unescape(final_link.group(1)))
    assert final_page.status_code == 200
    assert final_page.text.count('data-status="') == 5
    assert "عملية ترقيم 204" in final_page.text
    final_previous = re.search(r'<a class="m-btn" href="([^"]+)">السابق</a>', final_page.text)
    assert final_previous is not None
    assert "عملية ترقيم 100" in client.get(unescape(final_previous.group(1))).text

    returned = client.get(unescape(previous_link.group(1)))
    assert returned.status_code == 200
    assert returned.text.count('data-status="') == 100
    assert "عملية ترقيم 000" in returned.text

    filtered = client.get("/maintenance/periodic", params={"state": "بلا سجل"})
    assert filtered.status_code == 200
    assert 'value="بلا سجل" selected' in filtered.text
    assert "عرض 100 من 205 متابعة مطابقة" in filtered.text
    search = client.get("/maintenance/periodic", params={"q": "MODEL-COND-A"})
    assert search.status_code == 200
    assert "عرض 100 من 205 متابعة مطابقة" in search.text
    no_matches = client.get("/maintenance/periodic", params={"q": "NO-SUCH-EQUIPMENT"})
    assert no_matches.status_code == 200
    assert "عرض 0 من 0 متابعة مطابقة" in no_matches.text
    assert "إجمالي المتابعات</div><div class=\"kpi-value\">205" in no_matches.text
    assert client.get("/maintenance/periodic?after=invalid").status_code == 400


def test_operation_is_not_applicable_to_a_model_without_a_relation():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = Session()
    try:
        equipment_type = EquipmentType(name="نوع اختبار الانطباق", measurement_unit="km")
        db.add(equipment_type)
        db.flush()
        model_a = EquipmentModel(name="طراز الانطباق أ", equipment_type_id=equipment_type.id)
        model_b = EquipmentModel(name="طراز الانطباق ب", equipment_type_id=equipment_type.id)
        db.add_all([model_a, model_b])
        db.flush()
        operation = MaintenanceOperation(name="عملية الانطباق", interval_km=Decimal("5000"))
        db.add(operation)
        db.flush()
        _link(db, operation, model_a, interval_km=Decimal("5000"))
        db.commit()
        db.refresh(operation)

        equipment_a = Equipment(asset_code="APPL-A", equipment_type_id=equipment_type.id, equipment_model_id=model_a.id)
        equipment_b = Equipment(asset_code="APPL-B", equipment_type_id=equipment_type.id, equipment_model_id=model_b.id)
        db.add_all([equipment_a, equipment_b])
        db.commit()

        assert validate_operation_applicable_to_equipment(db, operation, equipment_a) is None
        assert validate_operation_applicable_to_equipment(db, operation, equipment_b) is not None
    finally:
        db.close()


def test_the_condition_of_one_model_never_moves_to_another_model():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = Session()
    try:
        equipment_type = EquipmentType(name="نوع اختبار الاستقلال", measurement_unit="km")
        db.add(equipment_type)
        db.flush()
        model_a = EquipmentModel(name="طراز الاستقلال أ", equipment_type_id=equipment_type.id)
        model_b = EquipmentModel(name="طراز الاستقلال ب", equipment_type_id=equipment_type.id)
        db.add_all([model_a, model_b])
        db.flush()
        operation = MaintenanceOperation(name="عملية الاستقلال", interval_km=Decimal("5000"))
        db.add(operation)
        db.flush()
        _link(db, operation, model_a, interval_km=Decimal("5000"))
        _link(db, operation, model_b, interval_km=Decimal("9000"))
        db.commit()

        # تعديل شرط طراز واحد فقط.
        db.execute(
            maintenance_operation_models.update()
            .where(
                maintenance_operation_models.c.operation_id == operation.id,
                maintenance_operation_models.c.equipment_model_id == model_a.id,
            )
            .values(interval_km=Decimal("15000"))
        )
        db.commit()

        assert operation_condition_for_model(db, operation.id, model_a.id).interval_km == Decimal("15000.0")
        assert operation_condition_for_model(db, operation.id, model_b.id).interval_km == Decimal("9000.0")
    finally:
        db.close()


def test_deleting_one_model_relation_keeps_the_other_model_condition():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = Session()
    try:
        equipment_type = EquipmentType(name="نوع اختبار حذف العلاقة", measurement_unit="hours")
        db.add(equipment_type)
        db.flush()
        model_a = EquipmentModel(name="طراز الحذف أ", equipment_type_id=equipment_type.id)
        model_b = EquipmentModel(name="طراز الحذف ب", equipment_type_id=equipment_type.id)
        db.add_all([model_a, model_b])
        db.flush()
        operation = MaintenanceOperation(name="عملية الحذف", interval_hours=Decimal("250"))
        db.add(operation)
        db.flush()
        _link(db, operation, model_a, interval_hours=Decimal("250"))
        _link(db, operation, model_b, interval_hours=Decimal("500"))
        db.commit()

        db.execute(
            maintenance_operation_models.delete().where(
                maintenance_operation_models.c.operation_id == operation.id,
                maintenance_operation_models.c.equipment_model_id == model_a.id,
            )
        )
        db.commit()

        assert operation_condition_for_model(db, operation.id, model_a.id).is_defined is False
        assert operation_condition_for_model(db, operation.id, model_b.id).interval_hours == Decimal("500.0")
    finally:
        db.close()


# ------------------------------------------------------------------- الـ API


def _operation_payload(name, conditions, warning_km=None, warning_days=None, **overrides):
    """حمولة إنشاء عملية كما ترسلها الواجهة: بلا أي قيمة قديمة على العملية.
    
    Warning settings are now at the operation level.
    """
    payload = {
        "name": name,
        "equipment_model_conditions": conditions,
    }
    warning_hours = overrides.get("warning_hours")
    if warning_km is None and warning_days is None and warning_hours is None:
        warning_km = 0
    if warning_km is not None:
        payload["warning_km"] = warning_km
    if warning_days is not None:
        payload["warning_days"] = warning_days
    payload.update(overrides)
    return payload


def test_api_returns_each_model_condition_of_the_same_operation(api):
    client, ids = api
    response = client.post(
        "/api/maintenance/operations",
        json=_operation_payload(
            "تغيير زيت المحرك",
            [
                {"model_id": ids["model_a"], "interval_km": 5000},
                {"model_id": ids["model_b"], "interval_km": 9000},
            ],
            warning_km=500,  # Unified warning at operation level
        ),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["condition_summary"]["condition"] == MULTIPLE_CONDITIONS_LABEL
    # Warning is unified at operation level, so all models show the same warning
    assert body["condition_summary"]["warning"] == "500 كم"
    assert body["condition_summary"]["has_multiple_conditions"] is True
    assert body["condition_source"] == "model_conditions"
    conditions = {row["model_id"]: row for row in body["model_conditions"]}
    assert conditions[ids["model_a"]]["condition_text"] == "5000 كم"
    assert conditions[ids["model_b"]]["condition_text"] == "9000 كم"
    assert conditions[ids["model_a"]]["model_name"] == "طراز ألف"
    # Warning text is the same for all models (from operation level)
    assert conditions[ids["model_a"]]["warning_text"] == "500 كم"
    assert conditions[ids["model_b"]]["warning_text"] == "500 كم"

    listed = client.get("/api/maintenance/operations").json()
    operation = next(item for item in listed if item["name"] == "تغيير زيت المحرك")
    assert operation["condition_summary"]["condition"] == MULTIPLE_CONDITIONS_LABEL
    assert operation["condition_summary"]["warning"] == "500 كم"


def test_api_edit_of_one_model_does_not_touch_the_other_model(api):
    client, ids = api
    created = client.post(
        "/api/maintenance/operations",
        json=_operation_payload(
            "عملية استقلال الطرازات",
            [
                {"model_id": ids["model_a"], "interval_km": 5000},
                {"model_id": ids["model_b"], "interval_km": 9000},
            ],
        ),
    ).json()

    updated = client.put(
        f"/api/maintenance/operations/{created['id']}",
        json=_operation_payload(
            "عملية استقلال الطرازات",
            [
                {"model_id": ids["model_a"], "interval_km": 15000},
                {"model_id": ids["model_b"], "interval_km": 9000},
            ],
            warning_km=1500,  # Unified warning at operation level
        ),
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    conditions = {row["model_id"]: row for row in body["model_conditions"]}
    assert conditions[ids["model_a"]]["interval_km"] == "15000.0"
    # Warning is same for all models (from operation level)
    assert conditions[ids["model_a"]]["warning_text"] == "1500 كم"
    assert conditions[ids["model_b"]]["warning_text"] == "1500 كم"
    assert conditions[ids["model_b"]]["interval_km"] == "9000.0"


def test_api_shows_a_single_shared_condition_without_duplicating_the_operation(api):
    client, ids = api
    client.post(
        "/api/maintenance/operations",
        json=_operation_payload(
            "عملية شرط مشترك",
            [
                {"model_id": ids["model_a"], "interval_days": 90},
                {"model_id": ids["model_b"], "interval_days": 90},
            ],
            warning_days=7,  # Unified warning at operation level
        ),
    )
    listed = client.get("/api/maintenance/operations").json()
    matches = [item for item in listed if item["name"] == "عملية شرط مشترك"]
    assert len(matches) == 1, "صف واحد لكل عملية حتى مع عدة طرازات"
    assert matches[0]["condition_summary"]["condition"] == "90 يوم"
    assert matches[0]["condition_summary"]["warning"] == "7 يوم"
    assert matches[0]["condition_summary"]["unit"] == "يوم"


def test_api_reports_unset_condition_for_a_model_without_one(api):
    """طراز بلا شرط محفوظ: «الشرط غير محدد» + القيمة القديمة كمرجع فقط."""
    client, ids = api
    client.post(
        "/api/maintenance/operations",
        json=_operation_payload(
            "عملية شرط ناقص",
            [
                {"model_id": ids["model_a"], "interval_km": 5000},
                {"model_id": ids["model_b"], "condition_source": "unset"},
            ],
            warning_km=500,  # Unified warning at operation level
        ),
    )
    listed = client.get("/api/maintenance/operations").json()
    operation = next(item for item in listed if item["name"] == "عملية شرط ناقص")
    assert operation["condition_summary"]["condition"] == CONDITION_UNSET_LABEL
    # Warning is unified at operation level - shown in summary
    assert operation["condition_summary"]["warning"] == "500 كم"
    conditions = {row["model_id"]: row for row in operation["model_conditions"]}
    unset_row = conditions[ids["model_b"]]
    assert unset_row["is_defined"] is False
    assert unset_row["condition_text"] == "—"
    assert unset_row["unit_text"] == "—"
    # Unset condition shows "—" for warning_text (warning is in summary)
    assert unset_row["warning_text"] == "—"
    # القيمة القديمة على العملية لا تُعرض ولا تُرسل كمرجع في أي حقل.
    assert "legacy_condition_text" not in unset_row
    assert "legacy_warning_text" not in unset_row
    assert "interval_km" not in operation

    defined_row = conditions[ids["model_a"]]
    assert defined_row["is_defined"] is True


def test_api_shows_no_condition_for_an_operation_without_models(api):
    client, _ = api
    client.post("/api/maintenance/operations", json=_operation_payload("عملية بلا طراز", []))

    listed = client.get("/api/maintenance/operations").json()
    operation = next(item for item in listed if item["name"] == "عملية بلا طراز")
    assert operation["model_conditions"] == []
    assert operation["condition_summary"]["condition"] is None
    assert operation["condition_source"] == "none"


def test_api_ignores_the_legacy_shared_value_without_asking_for_a_decision(api):
    """القيمة القديمة على العملية لا تصبح شرطًا ولا تُنتج طلب قرار بنسخها."""
    client, ids = api
    client.post(
        "/api/maintenance/operations",
        json={
            "name": "عملية بقيمة قديمة مشتركة",
            "equipment_model_conditions": [{"model_id": ids["model_a"], "condition_source": "unset"}],
            "warning_km": 500,  # Unified warning at operation level
        },
    )
    listed = client.get("/api/maintenance/operations").json()
    operation = next(item for item in listed if item["name"] == "عملية بقيمة قديمة مشتركة")
    # لا شرط محفوظ لأي طراز ⇒ لا مصدر شرط، ولا مؤشر «قرار مطلوب».
    assert operation["condition_source"] == "none"
    assert operation["condition_summary"]["condition"] == CONDITION_UNSET_LABEL
    # Warning is from operation level
    assert operation["condition_summary"]["warning"] == "500 كم"
    assert operation["model_conditions"][0]["condition_text"] == "—"
    assert "condition_decision_required" not in operation


def test_api_removes_a_model_relation_when_it_is_no_longer_submitted(api):
    client, ids = api
    created = client.post(
        "/api/maintenance/operations",
        json=_operation_payload(
            "عملية إزالة طراز",
            [
                {"model_id": ids["model_a"], "interval_km": 5000},
                {"model_id": ids["model_b"], "interval_km": 9000},
            ],
        ),
    ).json()

    updated = client.put(
        f"/api/maintenance/operations/{created['id']}",
        json=_operation_payload("عملية إزالة طراز", [{"model_id": ids["model_b"], "interval_km": 9000}]),
    ).json()
    assert [row["model_id"] for row in updated["model_conditions"]] == [ids["model_b"]]
    assert updated["condition_summary"]["condition"] == "9000 كم"


def test_api_rejects_a_duplicated_model_in_the_same_operation(api):
    client, ids = api
    response = client.post(
        "/api/maintenance/operations",
        json=_operation_payload(
            "عملية طراز مكرر",
            [
                {"model_id": ids["model_a"], "interval_km": 5000},
                {"model_id": ids["model_a"], "interval_km": 9000},
            ],
        ),
    )
    assert response.status_code == 400
    assert "أكثر من مرة" in response.json()["detail"]


def test_api_rejects_an_unknown_model(api):
    client, _ = api
    response = client.post(
        "/api/maintenance/operations",
        json=_operation_payload("عملية طراز مجهول", [{"model_id": 99999, "interval_km": 5000}]),
    )
    assert response.status_code == 404


def test_api_toggle_activate_and_deactivate_keeps_the_model_conditions(api):
    client, ids = api
    created = client.post(
        "/api/maintenance/operations",
        json=_operation_payload(
            "عملية تعطيل وتفعيل",
            [{"model_id": ids["model_a"], "interval_km": 5000}],
            warning_km=500,  # Unified warning at operation level
        ),
    ).json()

    disabled = client.put(
        f"/api/maintenance/operations/{created['id']}",
        json=_operation_payload(
            "عملية تعطيل وتفعيل",
            [{"model_id": ids["model_a"], "interval_km": 5000}],
            warning_km=500,
            is_active=False,
        ),
    ).json()
    assert disabled["is_active"] is False
    assert disabled["model_conditions"][0]["condition_text"] == "5000 كم"
    assert disabled["model_conditions"][0]["warning_text"] == "500 كم"

    enabled = client.put(
        f"/api/maintenance/operations/{created['id']}",
        json=_operation_payload(
            "عملية تعطيل وتفعيل",
            [{"model_id": ids["model_a"], "interval_km": 5000}],
            warning_km=500,
            is_active=True,
        ),
    ).json()
    assert enabled["is_active"] is True
    assert enabled["model_conditions"][0]["warning_text"] == "500 كم"


def test_api_delete_removes_the_operation_and_its_model_relations(api):
    client, ids = api
    created = client.post(
        "/api/maintenance/operations",
        json=_operation_payload("عملية للحذف", [{"model_id": ids["model_a"], "interval_km": 5000}]),
    ).json()

    assert client.delete(f"/api/maintenance/operations/{created['id']}").status_code == 204
    db = Session()
    try:
        remaining = db.execute(
            maintenance_operation_models.select().where(
                maintenance_operation_models.c.operation_id == created["id"]
            )
        ).all()
        assert remaining == []
    finally:
        db.close()


def test_api_rejects_a_non_positive_model_interval(api):
    client, ids = api
    response = client.post(
        "/api/maintenance/operations",
        json=_operation_payload("عملية فاصل سالب", [{"model_id": ids["model_a"], "interval_km": -5}]),
    )
    assert response.status_code == 422


def test_api_requires_a_meter_reading_for_a_counter_unit_equipment(api):
    client, ids = api
    created = client.post(
        "/api/maintenance/operations",
        json=_operation_payload("عملية عدّاد", [{"model_id": ids["model_a"], "interval_km": 5000}]),
    ).json()

    response = client.post(
        "/api/maintenance/execution",
        json={
            "equipment_id": ids["equipment_a"],
            "operation_id": created["id"],
            "maintenance_date": str(date(2026, 9, 25)),
        },
    )
    assert response.status_code == 400
    assert "قراءة العداد" in response.json()["detail"]


def test_api_blocks_executing_an_operation_not_linked_to_the_equipment_model(api):
    client, ids = api
    created = client.post(
        "/api/maintenance/operations",
        json=_operation_payload("عملية طراز آخر", [{"model_id": ids["model_b"], "interval_km": 5000}]),
    ).json()

    response = client.post(
        "/api/maintenance/execution",
        json={
            "equipment_id": ids["equipment_a"],
            "operation_id": created["id"],
            "maintenance_date": str(date(2026, 9, 25)),
            "meter_value": 5000,
        },
    )
    assert response.status_code == 409
    assert "لا تنطبق على طراز" in response.json()["detail"]


# --------------------------------------------------------- الخطة مقابل العملية


def test_plan_membership_never_changes_the_model_condition(api):
    client, ids = api
    created = client.post(
        "/api/maintenance/operations",
        json=_operation_payload("عملية داخل خطة", [{"model_id": ids["model_a"], "interval_km": 10000}]),
    ).json()

    plan = client.post(
        "/api/maintenance/plans",
        json={"name": "خطة توافق", "equipment_model_id": ids["model_a"], "interval_km": 10000},
    )
    assert plan.status_code == 201, plan.text
    plan_id = plan.json()["id"]

    added = client.post(
        f"/api/maintenance/plans/{plan_id}/operations",
        json={"plan_id": plan_id, "operation_id": created["id"], "sort_order": 1},
    )
    assert added.status_code == 201, added.text

    after = next(
        item for item in client.get("/api/maintenance/operations").json() if item["id"] == created["id"]
    )
    assert after["model_conditions"][0]["interval_km"] == "10000.0"

    # تعديل الخطة لا يمس شرط العملية على الطراز.
    edited = client.put(
        f"/api/maintenance/plans/{plan_id}",
        json={"name": "خطة توافق معدلة", "equipment_model_id": ids["model_a"], "interval_km": 20000},
    )
    assert edited.status_code == 200
    after_edit = next(
        item for item in client.get("/api/maintenance/operations").json() if item["id"] == created["id"]
    )
    assert after_edit["model_conditions"][0]["interval_km"] == "10000.0"


def test_plan_operation_is_added_without_an_independent_model_condition(api):
    client, ids = api
    created = client.post(
        "/api/maintenance/operations",
        json=_operation_payload("عملية شرط الطراز أ", [{"model_id": ids["model_a"], "interval_km": 10000}]),
    ).json()

    plan = client.post(
        "/api/maintenance/plans",
        json={"name": "خطة طراز باء", "equipment_model_id": ids["model_b"], "interval_km": 10000},
    ).json()

    # طراز الخطة (باء) بلا شرط مستقل للعملية؛ عملية الخطة ترث شرط الخطة،
    # فلا يُشترط شرط طراز مستقل لإدراجها.
    accepted = client.post(
        f"/api/maintenance/plans/{plan['id']}/operations",
        json={"plan_id": plan["id"], "operation_id": created["id"], "sort_order": 1},
    )
    assert accepted.status_code == 201, accepted.text

    # ولم يُكتب شرط الخطة على العملية المشتركة: شرط الطراز (أ) يبقى كما هو،
    # وشرط الطراز (باء) — إن ظهر — يبقى بلا فاصل مستقل.
    operation = next(
        item for item in client.get("/api/maintenance/operations").json() if item["id"] == created["id"]
    )
    model_a_condition = next(
        item for item in operation["model_conditions"] if item["model_id"] == ids["model_a"]
    )
    assert model_a_condition["interval_km"] == "10000.0"

    model_b_condition = next(
        (item for item in operation["model_conditions"] if item["model_id"] == ids["model_b"]),
        None,
    )
    if model_b_condition is not None:
        assert model_b_condition["interval_km"] is None


def test_plan_conditions_are_independent_from_operation_conditions(api):
    client, ids = api
    created = client.post(
        "/api/maintenance/operations",
        json=_operation_payload("عملية شروط مستقلة", [{"model_id": ids["model_a"], "interval_days": 90}]),
    ).json()

    plan = client.post(
        "/api/maintenance/plans",
        json={"name": "خطة أيام مستقلة", "equipment_model_id": ids["model_a"], "interval_days": 30},
    ).json()

    # شرط الخطة (30 يومًا) لا يحل مكان شرط الطراز (90 يومًا).
    operation = next(
        item for item in client.get("/api/maintenance/operations").json() if item["id"] == created["id"]
    )
    assert operation["model_conditions"][0]["interval_days"] == 90
    assert operation["model_conditions"][0]["condition_text"] == "90 يوم"
    plan_row = next(item for item in client.get("/api/maintenance/plans").json() if item["id"] == plan["id"])
    assert plan_row["interval_days"] == 30


# ------------------------------------------------------------ سجلات التنفيذ


def test_existing_records_and_ids_survive_a_condition_change(api):
    client, ids = api
    created = client.post(
        "/api/maintenance/operations",
        json=_operation_payload("عملية بسجل", [{"model_id": ids["model_a"], "interval_km": 5000}]),
    ).json()

    record = client.post(
        "/api/maintenance/execution",
        json={
            "equipment_id": ids["equipment_a"],
            "operation_id": created["id"],
            "maintenance_date": str(date(2026, 9, 25)),
            "meter_value": 5000,
        },
    )
    assert record.status_code == 201, record.text
    record_id = record.json()["id"]

    # تغيير شرط الطراز بعد تنفيذ سابق لا يعيد تفسير التنفيذ ولا يحذفه.
    client.put(
        f"/api/maintenance/operations/{created['id']}",
        json=_operation_payload("عملية بسجل", [{"model_id": ids["model_a"], "interval_km": 7000}]),
    )

    rows = client.get("/api/maintenance/execution").json()
    assert [row["id"] for row in rows] == [record_id]
    assert rows[0]["operation_id"] == created["id"]
    assert rows[0]["meter_value"] == "5000.0"

    db = Session()
    try:
        stored = db.query(MaintenanceRecord).filter(MaintenanceRecord.id == record_id).one()
        assert stored.operation_id == created["id"]
    finally:
        db.close()


# ----------------------------------------------------------------- الترحيل


def _migration_revision():
    import migrations.versions.f5c253fe0ece_add_maintenance_operation_models_table as revision

    return revision


def _scratch_database(tmp_path, name: str):
    """قاعدة اختبارية مؤقتة مُوسَمة على المراجعة السابقة لترحيل شروط الطراز.

    الترحيل لا يُشغَّل أبدًا على قاعدة بيانات المشروع: كل استدعاء يذهب إلى ملف
    مؤقت يُبنى هنا، وفيه فقط ما تحتاجه المراجعة (جدولا المفتاحين + العلاقة).
    """
    from sqlalchemy import create_engine as create_sync_engine

    revision = _migration_revision()
    database = tmp_path / name
    scratch = create_sync_engine(f"sqlite:///{database}")
    with scratch.begin() as connection:
        connection.execute(text("CREATE TABLE equipment_models (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE maintenance_operations (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": revision.down_revision},
        )
    return scratch, database


def _alembic_config(database):
    from alembic.config import Config

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database}")
    return config


def test_revision_adds_condition_columns_and_keeps_existing_relation_rows(tmp_path):
    """الترحيل يضيف أعمدة الشرط ويحفظ صفوف العلاقة، وتكراره لا يفشل."""
    from alembic import command

    revision = _migration_revision()
    scratch, database = _scratch_database(tmp_path, "migration_relation.db")
    with scratch.begin() as connection:
        # الجدول في شكله الأول: بلا أعمدة شرط، مع صف علاقة قائم يجب ألا يُفقد.
        connection.execute(
            text(
                "CREATE TABLE maintenance_operation_models ("
                " operation_id INTEGER NOT NULL,"
                " equipment_model_id INTEGER NOT NULL,"
                " CONSTRAINT pk_maintenance_operation_models PRIMARY KEY (operation_id, equipment_model_id))"
            )
        )
        connection.execute(text("INSERT INTO equipment_models (id) VALUES (1)"))
        connection.execute(text("INSERT INTO maintenance_operations (id) VALUES (1)"))
        connection.execute(
            text("INSERT INTO maintenance_operation_models (operation_id, equipment_model_id) VALUES (1, 1)")
        )
    scratch.dispose()

    config = _alembic_config(database)
    command.upgrade(config, revision.revision)
    command.upgrade(config, revision.revision)  # تكرار التنفيذ لا يفشل

    engine_local = create_engine(f"sqlite:///{database}")
    with engine_local.connect() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("maintenance_operation_models")}
        assert {
            "condition_source",
            "interval_km",
            "interval_hours",
            "interval_days",
            "warning_km",
            "warning_days",
            "is_active",
        } <= columns
        rows = connection.execute(
            text("SELECT operation_id, equipment_model_id, condition_source FROM maintenance_operation_models")
        ).all()
        assert rows == [(1, 1, "unset")], "صف العلاقة محفوظ وشرطه غير محدد"
        stamped = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        assert stamped == revision.revision

        # لا قيمة قديمة نُسخت إلى الطراز، ولا شرط أُنشئ من العدم.
        assert connection.execute(
            text("SELECT COUNT(*) FROM maintenance_operation_models WHERE interval_km IS NOT NULL")
        ).scalar() == 0

    # التراجع يُزيل أعمدة الشرط فقط ويُبقي العلاقة وصفّها.
    command.downgrade(config, revision.down_revision)
    with engine_local.connect() as connection:
        columns_after = {
            column["name"] for column in inspect(connection).get_columns("maintenance_operation_models")
        }
        assert "condition_source" not in columns_after
        remaining = connection.execute(
            text("SELECT operation_id, equipment_model_id FROM maintenance_operation_models")
        ).all()
        assert remaining == [(1, 1)], "التراجع لا يحذف علاقة العملية بالطراز"
    engine_local.dispose()


def test_revision_creates_the_relation_table_when_it_is_missing(tmp_path):
    """قاعدة مُوسَمة على المراجعة السابقة بلا جدول علاقة: الترحيل ينشئه كاملًا."""
    from alembic import command

    revision = _migration_revision()
    scratch, database = _scratch_database(tmp_path, "migration_fresh.db")
    scratch.dispose()

    command.upgrade(_alembic_config(database), revision.revision)

    engine_local = create_engine(f"sqlite:///{database}")
    with engine_local.connect() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("maintenance_operation_models")}
        assert {
            "operation_id",
            "equipment_model_id",
            "condition_source",
            "interval_km",
            "interval_hours",
            "interval_days",
            "warning_km",
            "warning_days",
            "is_active",
        } <= columns
        foreign_keys = {
            fk["referred_table"] for fk in inspect(connection).get_foreign_keys("maintenance_operation_models")
        }
        assert foreign_keys == {"equipment_models", "maintenance_operations"}
    engine_local.dispose()


def _constraint_revision():
    import migrations.versions.a7d1c40f5b2e_drop_operation_interval_constraint as revision

    return revision


def test_revision_drops_the_operation_interval_constraint_and_keeps_rows(tmp_path):
    """إزالة قيد «فاصل واحد على الأقل» مع الحفاظ على كل صف وقيمته القديمة."""
    from alembic import command
    from sqlalchemy import create_engine as create_sync_engine

    constraint_revision = _constraint_revision()
    database = tmp_path / "migration_constraint.db"
    scratch = create_sync_engine(f"sqlite:///{database}")
    with scratch.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": constraint_revision.down_revision},
        )
        # جدول العمليات بقيد الفاصل القديم، مع صفّين: أحدهما بقيمة قديمة.
        connection.execute(
            text(
                "CREATE TABLE maintenance_operations ("
                " id INTEGER NOT NULL,"
                " name VARCHAR(120) NOT NULL,"
                " interval_km NUMERIC(10,1),"
                " interval_hours NUMERIC(10,1),"
                " interval_days INTEGER,"
                " warning_km NUMERIC(10,1),"
                " warning_days INTEGER,"
                " is_active BOOLEAN NOT NULL DEFAULT 1,"
                " description TEXT,"
                " group_id INTEGER,"
                " CONSTRAINT pk_maintenance_operations PRIMARY KEY (id),"
                " CONSTRAINT ck_maintenance_operation_has_interval"
                " CHECK (interval_km IS NOT NULL OR interval_hours IS NOT NULL OR interval_days IS NOT NULL))"
            )
        )
        connection.execute(
            text(
                "INSERT INTO maintenance_operations (id, name, interval_km, interval_days) "
                "VALUES (1, 'بقيمة قديمة', 5000, 90)"
            )
        )
    scratch.dispose()

    config = _alembic_config(database)
    command.upgrade(config, constraint_revision.revision)
    command.upgrade(config, constraint_revision.revision)  # تكرار التنفيذ لا يفشل

    engine_local = create_engine(f"sqlite:///{database}")
    with engine_local.connect() as connection:
        constraints = {c["name"] for c in inspect(connection).get_check_constraints("maintenance_operations")}
        assert "ck_maintenance_operation_has_interval" not in constraints
        rows = connection.execute(
            text("SELECT id, name, interval_km, interval_days FROM maintenance_operations")
        ).all()
        assert rows == [(1, "بقيمة قديمة", 5000, 90)], "الصف وقيمته القديمة محفوظان"
        # وأصبح من الممكن وجود عملية بلا أي فاصل على مستواها.
        connection.execute(
            text("INSERT INTO maintenance_operations (id, name) VALUES (2, 'عملية عامة بلا فاصل')")
        )
        connection.commit()
        count = connection.execute(text("SELECT COUNT(*) FROM maintenance_operations")).scalar()
        assert count == 2
    engine_local.dispose()
