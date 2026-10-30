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
    ("/spare-parts-received", "سجل قطع الغيار المستلم"),
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
    assert 'id="openCatalogAdd"' in page.text
    assert 'id="openCategoryAdd"' in page.text
    assert 'id="catalogAddDialog"' in page.text
    assert 'id="categoryAddDialog"' in page.text
    assert 'id="closeCategoryAdd"' in page.text
    assert '<select name="category">' in page.text
    catalog_header = page.text.split('<thead>', 1)[1].split('</thead>', 1)[0]
    assert catalog_header.count("<tr>") == 1
    assert all(f"data-mt-force-filter>{heading}</th>" in catalog_header for heading in ("الاسم", "الرمز التعريفي", "طراز العتاد", "الفئة", "الصورة", "الحالة / تعديل"))
    assert 'class="scroll mt-table-theme-green" data-mt-region' in page.text
    assert 'class="header-filter-menu"' not in page.text
    assert 'class="actions">\n      <label>بحث' not in page.text
    assert 'action="/spare-parts/catalog/categories"' in page.text
    assert page.text.index('id="openCatalogAdd"') < page.text.index('id="openCategoryAdd"')
    assert 'action="/spare-parts/catalog/parts"' in page.text
    assert 'href="/spare-parts/catalog/import">استيراد الكتالوج</a>' in page.text
    navigation = page.text.split('id="appModuleNav"', 1)[1].split("</nav>", 1)[0]
    assert 'href="/spare-parts/catalog/import"' not in navigation
    assert "['/spare-parts/catalog/import','استيراد الكتالوج']" not in page.text

    category = client.post(
        "/spare-parts/catalog/categories",
        data={"name_ar": "تصنيف صفحة تجريبي", "name_fr": "Catégorie de test"},
        follow_redirects=False,
    )
    assert category.status_code == 303
    category_page = client.get("/spare-parts/catalog")
    assert 'option value="تصنيف صفحة تجريبي">تصنيف صفحة تجريبي</option>' in category_page.text
    category_form = next(
        form for form in re.findall(r'<form class="category-edit-form"[^>]*>.*?</form>', category_page.text, re.DOTALL)
        if 'value="تصنيف صفحة تجريبي"' in form
    )
    category_id = re.search(r'action="/spare-parts/catalog/categories/(\d+)/update"', category_form).group(1)
    assert f'action="/spare-parts/catalog/categories/{category_id}/delete"' in category_page.text

    child_category = client.post(
        "/spare-parts/catalog/categories",
        data={"name_ar": "تصنيف فرعي تجريبي", "parent_id": category_id},
        follow_redirects=False,
    )
    assert child_category.status_code == 303
    blocked_parent_delete = client.post(f"/spare-parts/catalog/categories/{category_id}/delete", follow_redirects=False)
    assert blocked_parent_delete.status_code == 409
    assert "يحتوي تصنيفات فرعية" in blocked_parent_delete.text
    category_page = client.get("/spare-parts/catalog")
    child_form = next(
        form for form in re.findall(r'<form class="category-edit-form"[^>]*>.*?</form>', category_page.text, re.DOTALL)
        if 'value="تصنيف فرعي تجريبي"' in form
    )
    child_id = re.search(r'action="/spare-parts/catalog/categories/(\d+)/update"', child_form).group(1)
    deleted_child = client.post(f"/spare-parts/catalog/categories/{child_id}/delete", follow_redirects=False)
    assert deleted_child.status_code == 303

    updated_category = client.post(
        f"/spare-parts/catalog/categories/{category_id}/update",
        data={"name_ar": "تصنيف صفحة معدل", "name_fr": "Catégorie modifiée"},
        follow_redirects=False,
    )
    assert updated_category.status_code == 303
    category_page = client.get("/spare-parts/catalog")
    assert 'option value="تصنيف صفحة معدل">تصنيف صفحة معدل</option>' in category_page.text

    created = client.post(
        "/spare-parts/catalog/parts",
        data={"name": "فلتر تجريبي", "name_ar": "فلتر", "reference": "PAGE-001", "manufacturer": "شركة اختبار", "category": "تصنيف صفحة معدل"},
        follow_redirects=False,
    )
    assert created.status_code == 303
    catalog_page = client.get("/spare-parts/catalog")
    assert "فلتر" in catalog_page.text
    assert "تصنيف صفحة معدل" in catalog_page.text
    catalog_filtered = client.get(
        "/spare-parts/catalog",
        params={"q": "PAGE-001", "category_id": category_id, "manufacturer": "شركة اختبار", "active": "true"},
    )
    assert catalog_filtered.status_code == 200
    assert "فلتر" in catalog_filtered.text
    blocked_delete = client.post(f"/spare-parts/catalog/categories/{category_id}/delete", follow_redirects=False)
    assert blocked_delete.status_code == 409
    assert "مرتبط بقطع غيار" in blocked_delete.text

    unused_category = client.post(
        "/spare-parts/catalog/categories",
        data={"name_ar": "تصنيف صفحة للحذف"},
        follow_redirects=False,
    )
    assert unused_category.status_code == 303
    category_page = client.get("/spare-parts/catalog")
    delete_ids = re.findall(r'action="/spare-parts/catalog/categories/(\d+)/delete"', category_page.text)
    unused_category_id = max(map(int, delete_ids))
    deleted_category = client.post(f"/spare-parts/catalog/categories/{unused_category_id}/delete", follow_redirects=False)
    assert deleted_category.status_code == 303
    assert "تصنيف صفحة للحذف" not in client.get("/spare-parts/catalog").text

    preview = client.post(
        "/spare-parts/catalog/import",
        files={"file": ("catalog.csv", "الاسم,الرمز التعريفي,طراز العتاد,الفئة,الصورة\nحشية,PAGE-002,طراز اختبار الصفحات,المحرك,\n".encode("utf-8"), "text/csv")},
    )
    assert preview.status_code == 200, preview.text
    assert "حشية" in preview.text
    for column in ("الاسم", "الرمز التعريفي", "طراز العتاد", "الفئة", "الصورة"):
        assert f"<th>{column}</th>" in preview.text
    assert preview.text.index("<th>الاسم</th>") < preview.text.index("<th>الرمز التعريفي</th>") < preview.text.index("<th>طراز العتاد</th>") < preview.text.index("<th>الفئة</th>") < preview.text.index("<th>الصورة</th>")
    batch_id = re.search(r"/spare-parts/catalog/import/(\d+)/apply", preview.text).group(1)
    result = client.post(
        f"/spare-parts/catalog/import/{batch_id}/apply",
        data={"row-0-include": "1"},
    )
    assert result.status_code == 200, result.text
    assert "أضيف 1" in result.text
    catalog = client.get("/spare-parts/catalog").text
    assert "PAGE-002" in catalog
    assert "طراز اختبار الصفحات" in catalog
    assert "المحرك" in catalog

    template = client.get("/spare-parts/catalog/import/template.xlsx")
    assert template.status_code == 200
    assert template.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    import io
    import openpyxl
    workbook = openpyxl.load_workbook(io.BytesIO(template.content), read_only=True)
    assert list(workbook.active.values)[0] == ("الاسم", "الرمز التعريفي", "طراز العتاد", "الفئة", "الصورة")
    workbook.close()


def test_spare_parts_catalog_can_delete_an_unused_part_from_its_row(pages):
    client, _ = pages
    created = client.post(
        "/spare-parts/catalog/parts",
        data={"name": "قطعة قابلة للحذف", "reference": "PAGE-DELETE-001"},
        follow_redirects=False,
    )
    assert created.status_code == 303

    page = client.get("/spare-parts/catalog")
    assert page.status_code == 200
    part_rows = re.findall(r"<tr>(.*?)</tr>", page.text, re.DOTALL)
    part_row = next((row for row in part_rows if "PAGE-DELETE-001" in row), None)
    assert part_row, "the newly created catalog item is missing from its row"
    delete_action = re.search(
        r'<form action="/spare-parts/catalog/parts/(\d+)/delete"[^>]*onsubmit="return confirm\(',
        part_row,
    )
    assert delete_action, "the catalog row is missing its confirmed delete action"
    part_id = delete_action.group(1)

    deleted = client.post(f"/spare-parts/catalog/parts/{part_id}/delete", follow_redirects=False)
    assert deleted.status_code == 303
    assert "PAGE-DELETE-001" not in client.get("/spare-parts/catalog").text


def test_maintenance_records_labels_equipment_number_as_registration(pages):
    client, _ = pages
    response = client.get("/maintenance/records")
    assert response.status_code == 200
    header = response.text.split('id="recordsTable"', 1)[1].split("</thead>", 1)[0]
    assert "رقم التسجيل" in header
    assert "رقم العتاد" not in response.text


def test_spare_parts_home_removes_duplicate_workflow_cards_and_bolds_indicators(pages):
    client, _ = pages
    response = client.get("/spare-parts")

    assert response.status_code == 200
    modules = response.text.split('<div class="modules">', 1)[1].split("</div>\n<section", 1)[0]
    assert modules.count('class="module-card"') == 1
    assert 'href="/spare-parts/catalog"' in modules
    for path in (
        "/spare-parts-requests",
        "/spare-parts-received",
        "/spare-parts-distribution",
        "/spare-parts-return",
    ):
        assert path not in modules
    assert ".spm .label{font-size:11px;font-weight:800" in response.text
    assert '<div class="overview">' in response.text
    assert ".spm .stats{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));grid-template-rows:repeat(2,minmax(0,1fr))" in response.text


def test_spare_parts_catalog_delete_preserves_parts_used_in_requests_or_repairs():
    from app.modules.faults_repairs.models import RepairPart, SparePart
    from app.modules.spare_parts_requests.models import SparePartRequest, SparePartRequestItem

    with _isolated_app() as (app, TestingSession, ids):
        with TestClient(app) as client:
            login = client.post(
                "/login",
                data={"username": SEEDED_USERNAME, "password": SEEDED_PASSWORD},
                follow_redirects=False,
            )
            assert login.status_code in (302, 303)

            with TestingSession() as db:
                repair_part = SparePart(part_number="CAT-USED-REPAIR", name="قطعة إصلاح")
                request_part = SparePart(part_number="CAT-USED-REQUEST", name="قطعة طلب")
                db.add_all([repair_part, request_part])
                db.flush()
                db.add(RepairPart(
                    repair_id=ids["repair"],
                    spare_part_id=repair_part.id,
                    quantity=1,
                    distribution_document="PAGE-REPAIR-DISTRIBUTION",
                ))
                request = db.query(SparePartRequest).filter_by(request_number="SPR-PAGE-1").one()
                db.add(SparePartRequestItem(
                    request_id=request.id,
                    spare_part_id=request_part.id,
                    requested_quantity=1,
                ))
                db.commit()
                part_ids = [repair_part.id, request_part.id]

            for part_id in part_ids:
                response = client.post(
                    f"/spare-parts/catalog/parts/{part_id}/delete",
                    follow_redirects=False,
                )
                assert response.status_code == 409

            with TestingSession() as db:
                assert all(db.get(SparePart, part_id) is not None for part_id in part_ids)


def test_tire_battery_procurement_and_asset_creation_work_end_to_end(pages):
    client, ids = pages
    receipt_day = date.today().isoformat()

    def create_received_request(number, asset_type, name, source_type, source_id):
        response = client.post("/api/spare-parts-requests", json={
            "request_number": number,
            "request_date": receipt_day,
            "received_date": receipt_day,
            "recipient": "مستلم الاختبار",
            "supplier_institution": "مورد الاختبار",
            "source_type": source_type,
            "source_id": source_id,
            "items": [{
                "asset_type": asset_type,
                "part_name": name,
                "requested_quantity": 1,
                "received_quantity": 1,
            }],
        })
        assert response.status_code == 201, response.text
        assert response.json()["status"] == "approved"
        return response.json()["items"][0]["id"]

    tire_item_id = create_received_request("E2E-TIRE-REQ", "tire", "إطار اختبار 1", "fault", ids["fault"])
    battery_fault = client.post("/api/faults-repairs/faults", json={
        "equipment_id": ids["equipment"],
        "reported_date": receipt_day,
        "description": "عطل بطارية لاختبار الاستلام الموحد",
        "severity": "low",
    })
    assert battery_fault.status_code == 201, battery_fault.text
    battery_item_id = create_received_request("E2E-BATTERY-REQ", "battery", "بطارية AGM اختبار", "fault", battery_fault.json()["id"])
    assert client.get("/api/spare-parts-requests/asset-receipts").status_code == 404
    tire_invalid = client.post("/tires", data={"serial_number": "E2E-T-INVALID", "acquisition_request_item_id": 999999})
    assert tire_invalid.status_code == 400
    tire_created = client.post("/tires", data={"serial_number": "E2E-T-1", "brand": "Brand", "model": "Model", "acquisition_request_item_id": tire_item_id}, follow_redirects=False)
    assert tire_created.status_code == 303
    tires_html = client.get("/tires").text
    assert "E2E-T-1" in tires_html
    tire_id = re.search(r'href="/tires/(\d+)"', tires_html).group(1)
    assert client.post(f"/tires/{tire_id}/delete", follow_redirects=False).status_code == 303

    battery_invalid = client.post("/batteries", data={"battery_type": "AGM", "acquisition_request_item_id": 999999})
    assert battery_invalid.status_code == 400
    battery_created = client.post("/batteries", data={"battery_type": "AGM", "brand": "Brand", "capacity": "60 Ah", "acquisition_request_item_id": battery_item_id}, follow_redirects=False)
    assert battery_created.status_code == 303
    batteries_html = client.get("/batteries").text
    assert "AGM" in batteries_html
    battery_id = re.search(r'href="/batteries/(\d+)"', batteries_html).group(1)
    battery_detail = client.get(f"/batteries/{battery_id}")
    assert battery_detail.status_code == 200
    assert "E2E-BATTERY-REQ" in battery_detail.text
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


def test_equipment_analysis_pages_avoid_duplicate_sections_and_raw_states(pages):
    client, _ = pages

    capacity = client.get("/equipment/analysis")
    assert capacity.status_code == 200
    assert "القدرة حسب النوع" in capacity.text
    assert "قواعد القراءة" not in capacity.text
    assert "ما الذي يستدعي الانتباه؟" not in capacity.text
    assert "جاهز فنيًا" in capacity.text
    assert "في مهمة" in capacity.text

    operational = client.get("/equipment/analysis/operational")
    assert operational.status_code == 200
    assert "تفاصيل عينة المقارنة متاحة داخل كل صف" in operational.text
    assert "<summary>العينة</summary>" in operational.text
    assert "مرجع الأعطال" not in operational.text
    assert "جاهز / في مهمة" in operational.text
    assert "ready / in_mission" not in operational.text


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
