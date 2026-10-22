"""صفحات HTML مُصادَق عليها — أول اختبار يعرض الصفحات فعلاً.

`pytest` وحده لا يرسم صفحة واحدة: كل مسمّى `TemplateResponse` قديم (39 موضعاً)
وانهيار معيار `WHERE` الفارغ في SQLAlchemy مرّا من هنا دون أن يمسكهما أي اختبار.
هذا الملف يبني قاعدة SQLite مؤقتة ببذور (عتاد + مهمة جارية + عطل + تصليح)،
يسجّل الدخول بمستخدم حقيقي، ثم يطلب كل صفحة ويتحقّق من عرضها.

لماذا هذا مهم: أي قBroken في Jinja أو استعلام أو صلاحية يظهر هنا كـ500 بدل أن
يصل إلى المستخدم. الخدمة الحقيقية للقاعدة لا تُلمس: `get_db` و`SessionLocal`
كلاهما موجَّه إلى المحرك المؤقت.
"""

import re
from contextlib import contextmanager
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import model_registry  # noqa: F401  (يسجّل كل النماذج قبل create_all)
from app.database import session as session_module
from app.database.base import Base
from web import main


# الصفحات التي كانت تُفحص يدوياً فقط، + صفحة تفصيل واحدة لكل وحدة Raises.
PAGE_MARKERS = [
    ("/dashboard", "التنبيهات الموحّدة"),
    ("/equipment", "العتاد"),
    ("/equipment/numerical-status", "الحالة العددية للعتاد"),
    ("/equipment-types", "مركز البيانات الأساسية"),
    ("/meter-readings", "العدادات"),
    ("/meter-readings/operations", None),
    ("/maintenance", "الصيانة"),
    ("/maintenance/periodic", None),
    ("/maintenance/plans", None),
    ("/maintenance/rules", None),
    ("/maintenance/catalog-imports", "كتالوجات الصيانة الفنية"),
    ("/faults-repairs", "الأعطال"),
    ("/faults-repairs/faults", None),
    ("/faults-repairs/repairs", None),
    ("/faults-repairs/analytics", None),
    ("/tires", "الإطارات"),
    ("/tires/inventory", None),
    ("/batteries", "البطاريات"),
    ("/spare-parts-received", "استلام الإطارات والبطاريات"),
    ("/spare-parts/catalog", "كتالوج قطع الغيار"),
    ("/fuel", "الوقود"),
    ("/missions", "المهمات"),
    ("/missions/drivers", "المهمات والسائقون"),
    ("/users", None),
]

SEEDED_USERNAME = "page-tester"
SEEDED_PASSWORD = "Test@12345"


def _seed(db):
    """بذور صغيرة لكنها حقيقية: عتاد مربوط بمهمة، عطل بتصليح، ومستخدم."""
    from app.core.security import hash_password
    from app.modules.equipment.models import Equipment
    from app.modules.equipment_types.models import EquipmentModel, EquipmentType
    from app.modules.faults_repairs.models import Fault, Repair
    from app.modules.spare_parts_requests.models import SparePartRequest
    from app.modules.missions import services as mission_service
    from app.modules.users.models import User

    user = User(
        username=SEEDED_USERNAME,
        full_name="مستخدم الاختبار",
        hashed_password=hash_password(SEEDED_PASSWORD),
        role="admin",
    )
    db.add(user)

    equipment_type = EquipmentType(name="شاحنات نقل", measurement_unit="km")
    db.add(equipment_type)
    db.flush()
    model = EquipmentModel(name="طراز اختبار الصفحات", equipment_type_id=equipment_type.id)
    db.add(model)
    db.flush()
    equipment = Equipment(
        asset_code="PAGE-1",
        registration_number="111-TEST",
        equipment_type_id=equipment_type.id,
        equipment_model_id=model.id,
        technical_condition="ready",
        operational_status="available",
    )
    db.add(equipment)
    db.flush()

    fault = Fault(
        equipment_id=equipment.id,
        reported_date=date.today(),
        fault_type="تعطل محرك",
        description="وصف العطل التجريبي",
        severity="high",
        status="open",
        exploitation_impact="limited",
        created_by_id=user.id,
    )
    db.add(fault)
    db.flush()

    repair = Repair(
        fault_id=fault.id,
        repair_date=date.today(),
        workshop_type="internal",
        status="in_progress",
        action_taken="فحص أولي",
    )
    db.add(repair)
    db.flush()

    # طلب الغيار مرتبط بالتصليح، والتصليح مرتبط بالعطل. يجب أن يظهر الطلب
    # في سجل الأعطال أيضاً، لا أن يختفي لأن fault_id في الطلب نفسه فارغ.
    spare_request = SparePartRequest(
        request_number="SPR-PAGE-1",
        request_date=date.today(),
        source_type="repair",
        repair_id=repair.id,
        equipment_id=equipment.id,
        status="pending",
        requested_by_id=user.id,
    )
    db.add(spare_request)
    db.commit()

    # المهمة تُنشأ عبر الخدمة لا عبر INSERT: `add_mission` هي المسار الوحيد الذي
    # يضبط `operational_status = in_mission`، واللوحة تقرأ ذلك الحقل المخزّن
    # (بعكس قائمة العتاد التي تحسب الوضعية الفعّالة). البذور يجب أن تمرّ
    # بالمسار نفسه الذي يمرّ به المستخدم، وإلا اختبرنا حالة لا تحدث أبداً.
    mission_service.add_mission(
        db,
        {
            "equipment_id": equipment.id,
            "driver_name": "سائق الاختبار",
            "start_date": date.today() - timedelta(days=2),
            "end_date": None,
        },
    )
    db.refresh(equipment)

    return {
        "user": user.id,
        "equipment": equipment.id,
        "fault": fault.id,
        "repair": repair.id,
    }


@contextmanager
def _isolated_app():
    """قاعدة مؤقتة + تطبيق معزول. العزل مضمون على مستويين."""
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

    with pytest.MonkeyPatch.context() as patch:
        # 1) لا تهيئة قاعدة في الاختبار: التطبيق الحقيقي يتولّاها عند التشغيل.
        patch.setattr(main, "init_db", lambda: None)
        patch.setattr(main, "create_default_admin", lambda: None)
        # 2) أي استيراد داخلي لـSessionLocal (مثل سجل التدقيق) يذهب للمؤقت أيضاً.
        patch.setattr(session_module, "SessionLocal", TestingSession)

        app = main.create_app()
        app.dependency_overrides[session_module.get_db] = override_get_db
        yield app, TestingSession, ids


@pytest.fixture(scope="module")
def pages():
    """قاعدة مؤقتة + عميل مُصادَق. العزل مضمون على مستويين."""
    with _isolated_app() as (app, _TestingSession, ids):
        with TestClient(app) as client:
            response = client.post(
                "/login",
                data={"username": SEEDED_USERNAME, "password": SEEDED_PASSWORD},
                follow_redirects=False,
            )
            assert response.status_code in (302, 303), "فشل تسجيل الدخول"
            yield client, ids


@pytest.fixture(scope="module")
def anonymous():
    """نفس القاعدة المعزولة، لكن بلا أي تسجيل دخول (تعطيل المصادقة المؤقت)."""
    with _isolated_app() as (app, TestingSession, ids):
        with TestClient(app) as client:
            yield client, ids, TestingSession


def test_login_sets_a_session_that_authenticates_the_pages(pages):
    client, _ = pages
    assert client.cookies.get("fleet_session"), "لا كوكي جلسة بعد الدخول"


def test_spare_parts_catalog_add_and_import_preview_apply(pages):
    client, _ = pages
    page = client.get("/spare-parts/catalog")
    assert page.status_code == 200
    assert "كتالوج قطع الغيار" in page.text

    created = client.post(
        "/spare-parts/catalog/parts",
        data={"name": "فلتر تجريبي", "name_ar": "فلتر", "reference": "PAGE-001", "manufacturer": "شركة اختبار"},
        follow_redirects=False,
    )
    assert created.status_code == 303
    assert "فلتر" in client.get("/spare-parts/catalog").text

    preview = client.post(
        "/spare-parts/catalog/import",
        files={"file": ("catalog.csv", "reference,name,manufacturer\nPAGE-002,حشية,شركة اختبار\n".encode("utf-8"), "text/csv")},
    )
    assert preview.status_code == 200, preview.text
    assert "حشية" in preview.text
    import re
    batch_id = re.search(r"/spare-parts/catalog/import/(\d+)/apply", preview.text).group(1)
    result = client.post(
        f"/spare-parts/catalog/import/{batch_id}/apply",
        data={"row-0-include": "1"},
    )
    assert result.status_code == 200, result.text
    assert "أضيف 1" in result.text
    assert "PAGE-002" in client.get("/spare-parts/catalog").text


def test_tire_battery_procurement_and_asset_creation_work_end_to_end(pages):
    client, _ = pages
    receipt_day = date.today().isoformat()
    for asset_type, number, description in (
        ("tire", "E2E-TIRE-RECEIPT", "إطار اختبار 1"),
        ("battery", "E2E-BATTERY-RECEIPT", "بطارية AGM اختبار"),
    ):
        response = client.post("/api/spare-parts-requests/asset-receipts", json={
            "asset_type": asset_type,
            "document_number": number,
            "description": description,
            "quantity": 1,
            "received_date": receipt_day,
            "supplier": "مورد الاختبار",
            "recipient": "مستلم الاختبار",
        })
        assert response.status_code == 201, response.text

    tire_invalid = client.post("/tires", data={"serial_number": "E2E-T-INVALID", "acquisition_document": "UNKNOWN"})
    assert tire_invalid.status_code == 400
    tire_created = client.post("/tires", data={"serial_number": "E2E-T-1", "brand": "Brand", "model": "Model", "acquisition_document": "E2E-TIRE-RECEIPT"}, follow_redirects=False)
    assert tire_created.status_code == 303
    tires_html = client.get("/tires").text
    assert "E2E-T-1" in tires_html
    tire_id = re.search(r'href="/tires/(\d+)"', tires_html).group(1)
    assert client.post(f"/tires/{tire_id}/delete", follow_redirects=False).status_code == 303

    battery_invalid = client.post("/batteries", data={"battery_type": "AGM", "acquisition_document": "UNKNOWN"})
    assert battery_invalid.status_code == 400
    battery_created = client.post("/batteries", data={"battery_type": "AGM", "brand": "Brand", "model": "Model", "acquisition_document": "E2E-BATTERY-RECEIPT"}, follow_redirects=False)
    assert battery_created.status_code == 303
    batteries_html = client.get("/batteries").text
    assert "AGM" in batteries_html
    battery_id = re.search(r'href="/batteries/(\d+)"', batteries_html).group(1)
    battery_detail = client.get(f"/batteries/{battery_id}")
    assert battery_detail.status_code == 200
    assert "E2E-BATTERY-RECEIPT" in battery_detail.text
    assert client.post(f"/batteries/{battery_id}/delete", follow_redirects=False).status_code == 303


def test_faults_repairs_dashboard_shows_repair_metrics_by_status(pages):
    client, _ = pages
    response = client.get("/faults-repairs")

    assert response.status_code == 200
    start = response.text.index('<section class="repair-statuses"')
    end = response.text.index("</section>", start)
    repair_metrics = response.text[start:end]
    assert "قيد الإصلاح" in repair_metrics
    assert "تم الإصلاح" in repair_metrics
    assert "ملغى" not in repair_metrics
    assert re.findall(r'class="value">(\d+)</div>', repair_metrics) == ["1", "0"]


def test_pages_open_without_login(anonymous):
    """تعطيل المصادقة المؤقت: لا تحويل إلى /login ولا 401/403 لأي صفحة رئيسية."""
    client, _, _ = anonymous
    failures = []

    for path, marker in PAGE_MARKERS:
        response = client.get(path, follow_redirects=False)
        if response.status_code != 200:
            failures.append(f"{path} -> HTTP {response.status_code}")
            continue
        if marker and marker not in response.text:
            failures.append(f"{path} -> العلامة {marker!r} غير موجودة")

    assert failures == [], "\n".join(failures)


def test_api_endpoints_open_without_login(anonymous):
    """واجهات API المحمية بالمستخدم/الصلاحية تعمل بلا جلسة عند تعطيل المصادقة."""
    client, _, _ = anonymous

    me = client.get("/api/me")
    assert me.status_code == 200, me.text
    assert me.json()["username"] == SEEDED_USERNAME

    # نقطة كانت تتطلّب دور admin.
    users = client.get("/api/users")
    assert users.status_code == 200, users.text
    assert any(item["username"] == SEEDED_USERNAME for item in users.json())


def test_user_dependent_write_works_without_login(anonymous):
    """الإجراءات التي تكتب `current_user.id` لا تتعطّل بلا تسجيل دخول."""
    from app.modules.faults_repairs.models import Fault

    client, ids, TestingSession = anonymous
    response = client.post(
        "/api/faults-repairs/faults",
        json={
            "equipment_id": ids["equipment"],
            "reported_date": date.today().isoformat(),
            "description": "عطل أُنشئ بلا تسجيل دخول",
            "severity": "medium",
        },
    )
    assert response.status_code == 201, response.text

    db = TestingSession()
    try:
        created = db.query(Fault).filter(Fault.id == response.json()["id"]).first()
    finally:
        db.close()
    assert created is not None
    assert created.created_by_id == ids["user"], "created_by_id لم يُضبط على المستخدم الاحتياطي"


def test_every_page_renders_for_a_logged_in_user(pages):
    client, _ = pages
    failures = []

    for path, marker in PAGE_MARKERS:
        response = client.get(path)
        if response.status_code != 200:
            failures.append(f"{path} -> HTTP {response.status_code}")
            continue
        if "Traceback" in response.text:
            failures.append(f"{path} -> استثناء مسرّب في الصفحة")
            continue
        if marker and marker not in response.text:
            failures.append(f"{path} -> العلامة {marker!r} غير موجودة")

    assert failures == [], "\n".join(failures)


def test_single_form_pages_are_connected_to_the_shared_editor(pages):
    client, _ = pages
    for path, marker in (
        ("/fuel", 'class="fuel-form" data-em-root'),
        ("/missions", 'action="/missions" class="mission-form" data-em-root'),
        ("/tires/settings", 'action="/tires/settings" data-em-root'),
        ("/batteries/settings", 'action="/batteries/settings" class="record-form" data-em-root'),
        ("/tires", 'action="/tires" class="tire-form" data-em-root'),
        ("/batteries", 'action="/batteries" class="battery-form" data-em-root'),
    ):
        response = client.get(path)
        assert response.status_code == 200, response.text
        assert marker in response.text, f"النموذج لا يتتبع تغييره عبر الشريط: {path}"
        assert 'data-em-action="save"' in response.text

    meter_page = client.get('/meter-readings').text
    assert 'id="readingForm" action="/meter-readings/create" method="post" data-em-root' in meter_page
    assert "if(window.EditManager)EditManager.reset();openModal('readingModal')" in meter_page
    assert "if(id==='readingModal')" in meter_page

    maintenance_page = client.get('/maintenance/records')
    assert maintenance_page.status_code == 200, maintenance_page.text
    assert 'id="maintenanceRecordForm" class="toolbar" style="padding:18px;flex-wrap:wrap" data-em-root' in maintenance_page.text
    assert 'data-em-action="save"' in maintenance_page.text


def test_detail_pages_render(pages):
    """صفحات التفاصيل لم تكن مغطّاة إطلاقاً — أعطال/تصليح/عداد/تحرير عتاد."""
    client, ids = pages
    paths = [
        f"/equipment/{ids['equipment']}",
        f"/equipment/{ids['equipment']}/meters",
        f"/equipment/{ids['equipment']}/maintenance",
        f"/equipment/{ids['equipment']}/edit",
        f"/faults-repairs/faults/{ids['fault']}",
        f"/faults-repairs/repairs/{ids['repair']}",
    ]
    failures = [
        f"{path} -> HTTP {client.get(path).status_code}"
        for path in paths
        if client.get(path).status_code != 200
    ]

    assert failures == [], "\n".join(failures)
    meter_page = client.get(f"/equipment/{ids['equipment']}/meters").text
    assert '<form id="editReadingForm" method="post" data-em-root>' in meter_page
    assert 'data-em-action="save"' in meter_page
    assert "if(window.EditManager)EditManager.reset()" in meter_page
    maintenance_page = client.get(f"/equipment/{ids['equipment']}/maintenance").text
    assert f'action="/equipment/{ids["equipment"]}/maintenance/create" class="grid-form" data-em-root' in maintenance_page
    assert 'data-em-action="save"' in maintenance_page
    equipment_edit_page = client.get(f"/equipment/{ids['equipment']}/edit").text
    assert 'id="equipmentEditForm" data-em-root onsubmit=' in equipment_edit_page


def test_technician_detail_renders_analysis_for_assigned_repairs():
    from app.modules.faults_repairs.models import Technician, TechnicianIntervention

    with _isolated_app() as (app, TestingSession, ids):
        db = TestingSession()
        try:
            technician = Technician(
                employee_number="TECH-ANALYSIS-PAGE-1",
                full_name="فني اختبار الصفحة",
                specialization="ميكانيك",
            )
            db.add(technician)
            db.flush()
            db.add(TechnicianIntervention(
                repair_id=ids["repair"],
                technician_id=technician.id,
                intervention_date=date.today(),
                hours=2,
                work_description="فحص العطل",
            ))
            db.commit()
            technician_id = technician.id
        finally:
            db.close()

        with TestClient(app) as client:
            response = client.get(f"/faults-repairs/technicians/{technician_id}")

        assert response.status_code == 200, response.text
        assert "فني اختبار الصفحة" in response.text
        assert "عدد العتاد الذي تدخل عليه" in response.text
        assert ">1</b>" in response.text


def test_repair_workspace_uses_live_repair_and_has_four_sections(pages):
    client, ids = pages
    response = client.get(f"/faults-repairs/repairs/{ids['repair']}")
    assert response.status_code == 200
    body = response.text
    for heading in ("1. بيانات التصليح", "2. تدخلات الفنيين", "3. قطع الغيار", "4. سجل الإصلاحات السابقة"):
        assert heading in body
    assert f"العطل F-{ids['fault']:03d}" in body
    assert f"R-{ids['repair']:03d}" in body
    assert "R-002 · مثال لإصلاح سابق" not in body
    assert 'حالة الإصلاح للقراءة فقط' in body
    assert "تغيير حالة الإصلاح" not in body
    assert "SPR-PAGE-1" in body
    assert '<form id="repairForm" data-em-root>' in body


def test_repair_history_includes_same_equipment_and_excludes_other_equipment(anonymous):
    from app.modules.equipment.models import Equipment
    from app.modules.faults_repairs.models import Fault, Repair

    client, ids, TestingSession = anonymous
    db = TestingSession()
    try:
        current_fault = db.query(Fault).filter(Fault.id == ids["fault"]).one()
        same_equipment_fault = Fault(
            equipment_id=ids["equipment"], reported_date=date.today(),
            fault_type="عطل ناقل الحركة", description="فحص ناقل الحركة",
            severity="medium", status="repaired", exploitation_impact="none",
        )
        db.add(same_equipment_fault)
        db.flush()
        same_equipment_repair = Repair(
            fault_id=same_equipment_fault.id, repair_date=date.today() - timedelta(days=10),
            workshop_type="internal", status="completed", action_taken="صيانة ناقل الحركة",
        )
        other_equipment = Equipment(
            asset_code="PAGE-OTHER", registration_number="222-TEST",
            equipment_type_id=current_fault.equipment.equipment_type_id,
            equipment_model_id=current_fault.equipment.equipment_model_id,
            technical_condition="ready", operational_status="available",
        )
        db.add(other_equipment)
        db.flush()
        other_fault = Fault(
            equipment_id=other_equipment.id, reported_date=date.today(),
            fault_type="عطل مختلف", description="عتاد مختلف",
            severity="medium", status="repaired", exploitation_impact="none",
        )
        db.add_all([same_equipment_repair, other_fault])
        db.flush()
        db.add(Repair(
            fault_id=other_fault.id, repair_date=date.today() - timedelta(days=5),
            workshop_type="internal", status="completed", action_taken="إصلاح العتاد الآخر",
        ))
        db.commit()
    finally:
        db.close()

    response = client.get(f"/faults-repairs/repairs/{ids['repair']}")
    assert response.status_code == 200
    assert "صيانة ناقل الحركة" in response.text
    assert "إصلاح العتاد الآخر" not in response.text


def test_repair_workspace_saves_current_repair_and_rejects_reversed_dates(anonymous):
    client, ids, TestingSession = anonymous
    start = date.today() - timedelta(days=2)
    end = date.today() - timedelta(days=1)
    payload = {
        "repair_start_date": start.isoformat(),
        "repair_end_date": None,
        "meter_value": None,
        "diagnosis": "تشخيص محفوظ",
        "action_taken": "إجراء محفوظ",
        "workshop_type": "internal",
        "workshop": "الورشة الرئيسية",
        "repair_document": "DOC-TEST",
        "external_dispatch_document": None,
        "labor_hours": 3,
        "notes": "ملاحظة محفوظة",
    }
    saved = client.patch(f"/api/faults-repairs/repairs/{ids['repair']}", json=payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()["status"] == "in_progress"
    assert "إجراء محفوظ" in client.get(f"/faults-repairs/repairs/{ids['repair']}").text
    reversed_payload = dict(payload, repair_start_date=end.isoformat(), repair_end_date=start.isoformat())
    invalid = client.patch(f"/api/faults-repairs/repairs/{ids['repair']}", json=reversed_payload)
    assert invalid.status_code == 422
    db = TestingSession()
    try:
        from app.modules.faults_repairs.models import Repair
        repair = db.query(Repair).filter(Repair.id == ids["repair"]).one()
        assert repair.repair_start_date == start and repair.repair_end_date is None
        assert repair.status == "in_progress"
        assert repair.fault.status == "repairing"
        assert repair.fault_id == ids["fault"]
    finally:
        db.close()


def test_repair_workspace_adds_and_reopens_saved_technician_intervention(anonymous):
    client, ids, _TestingSession = anonymous
    technician = client.post("/api/faults-repairs/technicians", json={
        "employee_number": "TECH-PAGE-1", "full_name": "فني الاختبار", "is_active": True,
    })
    assert technician.status_code == 201, technician.text
    intervention = client.post("/api/faults-repairs/technician-interventions", json={
        "repair_id": ids["repair"], "technician_id": technician.json()["id"],
        "intervention_date": date.today().isoformat(), "hours": 2.5,
        "work_description": "فحص مضخة التبريد", "notes": "تم الحفظ",
    })
    assert intervention.status_code == 201, intervention.text
    body = client.get(f"/faults-repairs/repairs/{ids['repair']}").text
    assert "فني الاختبار" in body
    assert "فحص مضخة التبريد" in body
    assert "1 تدخلات محفوظة" in body
    edit = client.patch(f"/api/faults-repairs/technician-interventions/{intervention.json()['id']}", json={
        "technician_id": technician.json()["id"], "intervention_date": date.today().isoformat(),
        "hours": 3, "work_description": "اختبار الضغط", "notes": "محدث",
    })
    assert edit.status_code == 200, edit.text
    assert "اختبار الضغط" in client.get(f"/faults-repairs/repairs/{ids['repair']}").text
    deleted = client.delete(f"/api/faults-repairs/technician-interventions/{intervention.json()['id']}")
    assert deleted.status_code == 204
    assert "0 تدخلات محفوظة" in client.get(f"/faults-repairs/repairs/{ids['repair']}").text


def test_dashboard_shows_the_seeded_equipment_with_arabic_labels(pages):
    """ربط الاختبارَين: بيانات البذور تظهر في اللوحة بتسميات عربية."""
    client, _ = pages
    body = client.get("/dashboard").text

    assert "نسبة الجاهزية الفنية" in body
    assert "العتاد العاطل" in body
    assert "قيد التصليح — ورشة داخلية" in body
    assert "قيد التصليح — ورشة خارجية" in body
    assert "عتاد في مهمة" in body
    assert "طلبات قطع الغيار قيد الانتظار" in body
    for raw in ("available", "in_mission", "in_maintenance", "in_external_workshop", "unavailable"):
        assert f">{raw}<" not in body, f"مفتاح خام في اللوحة: {raw}"


def test_equipment_list_renders_the_effective_status_not_the_stored_one(pages):
    """العتاد مخزَّن `available` لكن لديه تصليح داخلي نشط ⇒ الواجهة تعرض الحالة الفعّالة."""
    client, ids = pages
    body = client.get("/equipment").text

    assert "111-TEST" in body, "العتاد المزروع غير ظاهر في القائمة"
    assert "في الصيانة" in body, "الوضعية الفعّالة لم تُعرض"
    assert 'data-status="in_maintenance"' in body, "البطاقة لم تحمل الوضعية الفعّالة"
    assert '<form method="post" action="/equipment/create" class="grid-form" id="equipmentCreateForm" data-em-root>' in body
    assert 'data-em-action="save"' in body


def test_fault_list_shows_spare_request_linked_through_repair(pages):
    client, _ = pages
    body = client.get("/faults-repairs/faults").text

    assert "SPR-PAGE-1" in body, "طلب الغيار المرتبط بالتصليح لا يظهر في سجل الأعطال"
    assert "حالة طلب الغيار" in body, "عمود حالة طلب الغيار غير موجود"
    assert "معلق" in body, "حالة طلب الغيار غير ظاهرة"
    assert '<form id="faultForm" data-em-root>' in body
    assert "EditManager.markSaved('dom')" in body


def test_technician_creation_form_is_tracked_by_the_shared_editor(pages):
    client, _ = pages
    response = client.get("/faults-repairs/technicians")
    assert response.status_code == 200
    assert '<form id="techForm" class="tech-form" data-em-root>' in response.text
    assert 'data-em-action="save"' in response.text


def test_fault_pages_show_arabic_status_and_severity(pages):
    """العطل المخزَّن `open`/`high` يجب ألا يظهر كمفتاح إنجليزي."""
    client, ids = pages
    body = client.get(f"/faults-repairs/faults/{ids['fault']}").text

    assert "مفتوح" in body, "حالة العطل غير مترجمة"
    assert "عالية" in body, "درجة الخطورة غير مترجمة"
    assert ">open<" not in body and ">high<" not in body
    assert "قيد الإصلاح" in body, "حالة التصليح غير مترجمة"
    assert ">in_progress<" not in body
