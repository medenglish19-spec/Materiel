"""شاشة «تسجيل صيانة جديدة» — الحقول العشرة، الفني الفعلي، والحفظ/الاسترجاع.

يحرس هذا الملف سلوك الشاشة ومسار الحفظ الخلفي معًا:

* ترتيب الحقول العشرة حرفيًا (الطراز، العتاد، الخطة، العملية، التاريخ،
  العداد، رقم أمر العمل، الفني المنفذ، الأعمال المنجزة، الملاحظة).
* أن الخطة تُصفّي العمليات لنفس الطراز فقط، وأن «رقم أمر العمل» حقل رقمي،
  وأن «الأعمال المنجزة» و«الملاحظة» حقلان منفصلان.
* أن الفني يُقرأ من بيانات حقيقية (جدول الفنيين) لا من قائمة ثابتة.
* أن الخلفية ترفض الطلبات غير المتوافقة حتى لو أُرسلت يدويًا.
* أن الترحيل يضيف العمودين دون فقدان أي صف موجود.

كل شيء على قاعدة مؤقتة معزولة؛ لا يُقرأ `fleet_assets.db`.
"""

from datetime import date
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import joinedload, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.dependencies import get_current_user
from app.database import model_registry  # noqa: F401  (يُكمل تسجيل كل الجداول)
from app.database import session as session_module
from app.database.base import Base
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentModel, EquipmentType
from app.modules.faults_repairs.models import Technician
from app.modules.maintenance.models import (
    MaintenanceOperation,
    MaintenancePlan,
    MaintenancePlanOperation,
    MaintenanceRecord,
    maintenance_operation_models,
)
from app.modules.maintenance.router import router as maintenance_router
from app.modules.maintenance.services import CONDITION_MODEL
from app.modules.meter_readings.models import MeterReading
from app.modules.users.models import User

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Session = sessionmaker(bind=engine, expire_on_commit=False)


def _link_operation_to_model(db, operation, model, interval_km=Decimal("5000")):
    db.execute(
        maintenance_operation_models.insert().values(
            operation_id=operation.id,
            equipment_model_id=model.id,
            condition_source=CONDITION_MODEL,
            interval_km=interval_km,
        )
    )


def _operation_option(body, option_id):
    """مقطع خيار العملية فقط (يحمل data-model-ids) لا خيار طراز/عتاد/خطة."""
    marker = f'<option value="{option_id}" data-model-ids='
    start = body.index(marker)
    return body[start:body.index(">", start)]


def _attribute(tag, name):
    marker = f'{name}="'
    start = tag.index(marker) + len(marker)
    return tag[start:tag.index('"', start)]


@pytest.fixture()
def api():
    """واجهة حقيقية على قاعدة مؤقتة معزولة (لا تُقرأ fleet_assets.db)."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = Session()
    equipment_type = EquipmentType(name="نوع اختبار سجل الصيانة", measurement_unit="km")
    db.add(equipment_type)
    db.flush()

    model_a = EquipmentModel(name="طراز ألف", equipment_type_id=equipment_type.id)
    model_b = EquipmentModel(name="طراز باء", equipment_type_id=equipment_type.id)
    db.add_all([model_a, model_b])
    db.flush()

    equipment_a = Equipment(
        asset_code="REC-A",
        registration_number="REC-A",
        equipment_type_id=equipment_type.id,
        equipment_model_id=model_a.id,
    )
    equipment_b = Equipment(
        asset_code="REC-B",
        registration_number="REC-B",
        equipment_type_id=equipment_type.id,
        equipment_model_id=model_b.id,
    )
    db.add_all([equipment_a, equipment_b])
    db.flush()

    technician = Technician(employee_number="T-100", full_name="محمد الفني", is_active=1)
    inactive = Technician(employee_number="T-200", full_name="فني غير نشط", is_active=0)
    db.add_all([technician, inactive])
    db.flush()

    operation_a = MaintenanceOperation(name="عملية طراز ألف", is_active=True)
    operation_a_extra = MaintenanceOperation(name="عملية ألف أخرى", is_active=True)
    operation_b = MaintenanceOperation(name="عملية طراز باء", is_active=True)
    operation_library = MaintenanceOperation(name="عملية عامة بلا طراز", is_active=True)
    db.add_all([operation_a, operation_a_extra, operation_b, operation_library])
    db.flush()
    _link_operation_to_model(db, operation_a, model_a)
    _link_operation_to_model(db, operation_a_extra, model_a)
    _link_operation_to_model(db, operation_b, model_b)
    # operation_library بلا أي ارتباط بطراز: يجب ألا تظهر لأي طراز.

    plan_a = MaintenancePlan(
        name="خطة طراز ألف",
        equipment_model_id=model_a.id,
        is_active=True,
        is_approved=True,
    )
    db.add(plan_a)
    db.flush()
    db.add(MaintenancePlanOperation(plan_id=plan_a.id, operation_id=operation_a.id))

    db.add(User(id=1, username="records-admin", full_name="مسؤول", hashed_password="x", role="admin", is_active=True))
    db.commit()
    ids = {
        "model_a": model_a.id,
        "model_b": model_b.id,
        "equipment_a": equipment_a.id,
        "equipment_b": equipment_b.id,
        "technician": technician.id,
        "inactive_technician": inactive.id,
        "operation_a": operation_a.id,
        "operation_a_extra": operation_a_extra.id,
        "operation_b": operation_b.id,
        "operation_library": operation_library.id,
        "plan_a": plan_a.id,
    }
    db.close()

    app = FastAPI()
    app.include_router(maintenance_router)

    def override_db():
        session = Session()
        try:
            yield session
        finally:
            session.close()

    def override_user():
        return User(id=1, username="records-admin", full_name="مسؤول", hashed_password="x", role="admin", is_active=True)

    app.dependency_overrides[session_module.get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    with TestClient(app) as client:
        yield client, ids


def _valid_payload(ids, **overrides):
    payload = {
        "equipment_id": ids["equipment_a"],
        "plan_id": ids["plan_a"],
        "operation_id": ids["operation_a"],
        "maintenance_date": date.today().isoformat(),
        "meter_value": "100",
        "work_order": "1234",
        "technician_id": ids["technician"],
        "description": "تغيير الزيت وتعبئة السائل",
        "note": "ملاحظة إضافية",
        "workshop": "الورشة الرئيسية",
    }
    payload.update(overrides)
    return payload


def _latest_record():
    db = Session()
    try:
        record = (
            db.query(MaintenanceRecord)
            .options(joinedload(MaintenanceRecord.technician))
            .order_by(MaintenanceRecord.id.desc())
            .first()
        )
        if record is not None:
            db.expunge(record)
        return record
    finally:
        db.close()


# --------------------------------------------------- ترتيب الحقول ومصادرها


def test_new_record_form_shows_the_ten_fields_in_the_exact_order(api):
    """الحقول العشرة بترتيبها الحرفي، ورقم أمر العمل رقمي، والعمل/الملاحظة نصّان متعدّدا الأسطر."""
    client, _ = api
    body = client.get("/maintenance/records").text
    order = [
        'id="modelFilter"',
        'name="equipment_id"',
        'name="plan_id"',
        'name="operation_id"',
        'name="maintenance_date"',
        'name="meter_value"',
        'name="work_order"',
        'name="technician_id"',
        'name="description"',
        'name="note"',
    ]
    positions = [body.index(token) for token in order]
    assert positions == sorted(positions), "ترتيب الحقول العشرة غير مطابق"
    assert len(set(positions)) == len(order)
    # رقم أمر العمل حقل رقمي لا حقل وصف نصي.
    assert 'name="work_order" type="number"' in body
    # الأعمال المنجزة والملاحظة منفصلان ومتعدّدا الأسطر.
    assert 'name="description" rows="2"' in body
    assert 'name="note" rows="2"' in body


def test_model_filter_and_equipment_carry_real_relations(api):
    """الطرازات الفعلية من القاعدة، وكل عتاد يحمل طرازه لتصفية العميل."""
    client, ids = api
    body = client.get("/maintenance/records").text
    assert 'id="modelFilter"' in body
    assert "طراز ألف" in body and "طراز باء" in body
    assert f'data-model-id="{ids["model_a"]}"' in body
    assert f'data-model-id="{ids["model_b"]}"' in body


def test_plan_option_carries_its_model_and_linked_operations(api):
    """الخطة الافتراضية «تنفيذ مستقل»، وكل خطة تحمل طرازها وعملياتها المرتبطة فعليًا."""
    client, ids = api
    body = client.get("/maintenance/records").text
    assert "تنفيذ مستقل — بدون خطة" in body
    assert f'data-operation-ids="{ids["operation_a"]},"' in body
    assert f'value="{ids["plan_a"]}"' in body


def test_operation_options_expose_model_linkage_not_equipment(api):
    """مصدر بيانات العمليات يربطها بالطراز لا بالعتاد، ولا تبقى فلترة على مستوى العتاد."""
    client, ids = api
    body = client.get("/maintenance/records").text
    assert "data-equipment-ids=" not in body, "يجب ألا تبقى فلترة عمليات على مستوى العتاد"
    assert f'data-model-ids="{ids["model_a"]}"' in body
    assert f'data-model-ids="{ids["model_b"]}"' in body


def test_operation_eligibility_never_lists_another_models_operation(api):
    """عملية طراز باء لا تحمل طراز ألف، وعملية طراز ألف لا تحمل طراز باء."""
    client, ids = api
    body = client.get("/maintenance/records").text

    option_a = _operation_option(body, ids["operation_a"])
    assert _attribute(option_a, "data-model-ids").split(",") == [str(ids["model_a"])]

    option_b = _operation_option(body, ids["operation_b"])
    assert _attribute(option_b, "data-model-ids").split(",") == [str(ids["model_b"])]


def test_library_only_operation_is_not_offered_to_any_model(api):
    """العملية العامة غير المرتبطة بأي طراز لا تحمل أي طراز فلا تظهر لأي اختيار."""
    client, ids = api
    body = client.get("/maintenance/records").text
    option = _operation_option(body, ids["operation_library"])
    assert _attribute(option, "data-model-ids") == ""


def test_operation_options_carry_meter_model_conditions(api):
    """ترتيب السمات يبقى متوافقًا: النموذج بعد الطراز ثم شروط العداد."""
    client, ids = api
    body = client.get("/maintenance/records").text
    option = _operation_option(body, ids["operation_a"])
    assert option.index("data-model-ids=") < option.index("data-meter-models=")
    assert f"{ids['model_a']}:1" in _attribute(option, "data-meter-models")


def test_model_without_eligible_operations_shows_the_empty_message(api):
    """عند غياب عمليات مرتبطة بالطراز تظهر رسالة عربية واضحة."""
    client, _ = api
    body = client.get("/maintenance/records").text
    assert 'id="operationEmptyHint"' in body
    assert "لا توجد عمليات صيانة مرتبطة بهذا الطراز" in body


def test_records_table_does_not_reintroduce_a_status_column(api):
    """لا يُعاد عمود «الحالة» الذي حُذف في كوميت لاحق."""
    client, _ = api
    body = client.get("/maintenance/records").text
    assert "<th>الحالة</th>" not in body


def test_technician_select_lists_only_active_real_technicians(api):
    """الفني من بيانات حقيقية: النشط فقط يظهر، والمصدر ليس قائمة ثابتة."""
    client, ids = api
    body = client.get("/maintenance/records").text
    assert f'<option value="{ids["technician"]}">محمد الفني' in body
    assert "فني غير نشط" not in body


# ------------------------------------------------ الحفظ والاسترجاع الكاملان


def test_create_persists_work_order_technician_work_done_and_note(api):
    """حفظ سجل كامل: العشرة حقول، مع فصل الأعمال المنجزة عن الملاحظة."""
    client, ids = api
    response = client.post("/maintenance/records/create", data=_valid_payload(ids))
    assert response.status_code == 200, response.text

    record = _latest_record()
    assert record is not None
    assert record.equipment_id == ids["equipment_a"]
    assert record.plan_id == ids["plan_a"]
    assert record.operation_id == ids["operation_a"]
    assert record.work_order == "1234"
    assert record.technician_id == ids["technician"]
    assert record.technician.full_name == "محمد الفني"
    assert record.description == "تغيير الزيت وتعبئة السائل"
    assert record.note == "ملاحظة إضافية"
    assert record.workshop == "الورشة الرئيسية"


def test_edit_form_repopulates_the_saved_fields(api):
    """إعادة فتح السجل للتعديل تُظهر القيم المحفوظة كاملة."""
    client, ids = api
    assert client.post("/maintenance/records/create", data=_valid_payload(ids)).status_code == 200
    record = _latest_record()

    body = client.get(f"/maintenance/records?edit={record.id}").text
    assert "تغيير الزيت وتعبئة السائل" in body
    assert "ملاحظة إضافية" in body
    assert 'value="1234"' in body
    start = body.index('id="editTechnician"')
    segment = body[start:body.index("</select>", start)]
    assert f'value="{ids["technician"]}"' in segment
    assert "selected" in segment


def test_update_changes_technician_note_and_work_order(api):
    """التعديل يحفظ الفني والملاحظة والأعمال ورقم أمر العمل الجديدة."""
    client, ids = api
    assert client.post("/maintenance/records/create", data=_valid_payload(ids)).status_code == 200
    record = _latest_record()

    update = _valid_payload(
        ids,
        plan_id="",
        operation_id=ids["operation_a"],
        work_order="5678",
        technician_id="",
        description="أعمال محدّثة",
        note="ملاحظة محدّثة",
    )
    response = client.post(f"/maintenance/records/{record.id}/update", data=update)
    assert response.status_code == 200, response.text

    refreshed = _latest_record()
    assert refreshed.work_order == "5678"
    assert refreshed.technician_id is None, "إفراغ الفني يجب أن يُحفظ"
    assert refreshed.description == "أعمال محدّثة"
    assert refreshed.note == "ملاحظة محدّثة"
    db = Session()
    try:
        readings = db.query(MeterReading).filter(MeterReading.equipment_id == ids["equipment_a"]).all()
        assert len(readings) == 1
        assert readings[0].source_reference == f"maintenance:{record.id}:meter"
        assert readings[0].odometer == Decimal("100")
    finally:
        db.close()


# --------------------------------------------------- تحقق الخلفية الحاسم


def test_create_rejects_an_operation_from_another_model(api):
    """عملية لا تنتمي لطراز العتاد تُرفض حتى لو أُرسلت يدويًا."""
    client, ids = api
    response = client.post(
        "/maintenance/records/create",
        data=_valid_payload(ids, plan_id="", operation_id=ids["operation_b"]),
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "error=operation_model" in response.headers["location"]


def test_create_rejects_a_library_only_operation(api):
    """عملية عامة غير مرتبطة بأي طراز تُرفض خلفيًا ولا تُنفَّذ على العتاد."""
    client, ids = api
    response = client.post(
        "/maintenance/records/create",
        data=_valid_payload(ids, plan_id="", operation_id=ids["operation_library"]),
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "error=operation_model" in response.headers["location"]


def test_update_rejects_an_operation_from_another_model(api):
    """التعديل يخضع لنفس التحقق: لا يمكن تبديل العملية بعملية طراز آخر."""
    client, ids = api
    assert client.post("/maintenance/records/create", data=_valid_payload(ids)).status_code == 200
    record = _latest_record()
    response = client.post(
        f"/maintenance/records/{record.id}/update",
        data=_valid_payload(ids, plan_id="", operation_id=ids["operation_b"]),
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "error=operation_model" in response.headers["location"]


def test_api_execution_rejects_an_operation_from_another_model(api):
    """واجهة التنفيذ ترفض عملية تخص طرازًا آخر حتى خارج الواجهة."""
    client, ids = api
    response = client.post(
        "/api/maintenance/execution",
        json={
            "equipment_id": ids["equipment_a"],
            "operation_id": ids["operation_b"],
            "maintenance_date": date.today().isoformat(),
            "meter_value": 100,
        },
    )
    assert response.status_code == 409, response.text


def test_create_rejects_an_operation_outside_the_selected_plan(api):
    """عملية تنتمي للطراز لكنها ليست ضمن الخطة المختارة تُرفض."""
    client, ids = api
    response = client.post(
        "/maintenance/records/create",
        data=_valid_payload(ids, operation_id=ids["operation_a_extra"]),
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "error=plan_operation" in response.headers["location"]


@pytest.mark.parametrize("technician_key", ["inactive_technician"])
def test_create_rejects_inactive_technician(api, technician_key):
    client, ids = api
    response = client.post(
        "/maintenance/records/create",
        data=_valid_payload(ids, technician_id=ids[technician_key]),
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "error=technician" in response.headers["location"]


def test_create_rejects_unknown_technician(api):
    client, ids = api
    response = client.post(
        "/maintenance/records/create",
        data=_valid_payload(ids, technician_id=999999),
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "error=technician" in response.headers["location"]


def test_create_rejects_non_numeric_work_order(api):
    """رقم أمر العمل رقمي: الوصف النصي يُرفض خلفيًا."""
    client, ids = api
    response = client.post(
        "/maintenance/records/create",
        data=_valid_payload(ids, work_order="WO-PLAN-1"),
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "error=work_order" in response.headers["location"]


def test_api_execution_validates_and_stores_the_technician(api):
    """واجهة التنفيذ ترفض الفني غير الصالح وتحفظ الفني الصالح والملاحظة."""
    client, ids = api
    bad = client.post(
        "/api/maintenance/execution",
        json={
            "equipment_id": ids["equipment_a"],
            "operation_id": ids["operation_a"],
            "maintenance_date": date.today().isoformat(),
            "technician_id": ids["inactive_technician"],
        },
    )
    assert bad.status_code == 409, bad.text

    good = client.post(
        "/api/maintenance/execution",
        json={
            "equipment_id": ids["equipment_a"],
            "operation_id": ids["operation_a"],
            "maintenance_date": date.today().isoformat(),
            "meter_value": 100,
            "technician_id": ids["technician"],
            "note": "من الواجهة البرمجية",
        },
    )
    assert good.status_code == 201, good.text
    body = good.json()
    assert body["technician_id"] == ids["technician"]
    assert body["note"] == "من الواجهة البرمجية"


# ------------------------------------------------------------- الترحيل


def test_model_declares_the_technician_and_note_columns():
    columns = MaintenanceRecord.__table__.columns
    assert "technician_id" in columns
    assert "note" in columns
    technician_fk = next(
        fk for fk in MaintenanceRecord.__table__.foreign_keys if fk.parent.name == "technician_id"
    )
    assert technician_fk.column.table.name == "workshop_technicians"
    assert technician_fk.ondelete == "SET NULL"


def test_migration_adds_columns_and_preserves_existing_rows(tmp_path):
    """الترحيل يضيف technician_id/note وفهرس المفتاح الأجنبي، ولا يفقد صفًا، والتراجع نظيف."""
    from alembic import command
    from alembic.config import Config

    import migrations.versions.d4a91c7e2f60_add_maintenance_record_technician_note as revision

    database = tmp_path / "migration_records.db"
    scratch = create_engine(f"sqlite:///{database}")
    with scratch.begin() as connection:
        connection.execute(text("CREATE TABLE workshop_technicians (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE equipment (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE maintenance_plans (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE maintenance_operations (id INTEGER PRIMARY KEY)"))
        connection.execute(
            text(
                "CREATE TABLE maintenance_records ("
                " id INTEGER NOT NULL,"
                " equipment_id INTEGER NOT NULL,"
                " operation_id INTEGER,"
                " plan_id INTEGER,"
                " work_order VARCHAR(80),"
                " description TEXT,"
                " CONSTRAINT pk_maintenance_records PRIMARY KEY (id),"
                " CONSTRAINT fk_maintenance_records_operation"
                " FOREIGN KEY(operation_id) REFERENCES maintenance_operations (id) ON DELETE RESTRICT,"
                " CONSTRAINT fk_maintenance_records_plan"
                " FOREIGN KEY(plan_id) REFERENCES maintenance_plans (id) ON DELETE SET NULL)"
            )
        )
        connection.execute(
            text(
                "INSERT INTO maintenance_records (id, equipment_id, work_order, description)"
                " VALUES (1, 1, '77', 'عمل سابق')"
            )
        )
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": revision.down_revision},
        )
    scratch.dispose()

    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database}")
    command.upgrade(config, revision.revision)
    command.upgrade(config, revision.revision)  # تكرار التنفيذ لا يفشل

    local = create_engine(f"sqlite:///{database}")
    with local.connect() as connection:
        columns = {column["name"] for column in inspect(connection).get_columns("maintenance_records")}
        assert {"technician_id", "note"} <= columns
        rows = connection.execute(
            text("SELECT id, work_order, description FROM maintenance_records")
        ).all()
        assert rows == [(1, "77", "عمل سابق")], "الترحيل لا يفقد الصفوف أو قيمها"
        referred = {
            fk["referred_table"] for fk in inspect(connection).get_foreign_keys("maintenance_records")
        }
        assert "workshop_technicians" in referred
        indexes = {index["name"] for index in inspect(connection).get_indexes("maintenance_records")}
        assert "ix_maintenance_records_technician_id" in indexes
        assert connection.execute(
            text("SELECT COUNT(*) FROM sqlite_master WHERE name LIKE '_alembic_tmp_%'")
        ).scalar() == 0
        assert connection.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar() == revision.revision
    local.dispose()

    command.downgrade(config, revision.down_revision)
    local = create_engine(f"sqlite:///{database}")
    with local.connect() as connection:
        columns_after = {column["name"] for column in inspect(connection).get_columns("maintenance_records")}
        assert "technician_id" not in columns_after
        assert "note" not in columns_after
        assert connection.execute(text("SELECT COUNT(*) FROM maintenance_records")).scalar() == 1
    local.dispose()
