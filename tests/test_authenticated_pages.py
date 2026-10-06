"""صفحات HTML مُصادَق عليها — أول اختبار يعرض الصفحات فعلاً.

`pytest` وحده لا يرسم صفحة واحدة: كل مسمّى `TemplateResponse` قديم (39 موضعاً)
وانهيار معيار `WHERE` الفارغ في SQLAlchemy مرّا من هنا دون أن يمسكهما أي اختبار.
هذا الملف يبني قاعدة SQLite مؤقتة ببذور (عتاد + مهمة جارية + عطل + تصليح)،
يسجّل الدخول بمستخدم حقيقي، ثم يطلب كل صفحة ويتحقّق من عرضها.

لماذا هذا مهم: أي قBroken في Jinja أو استعلام أو صلاحية يظهر هنا كـ500 بدل أن
يصل إلى المستخدم. الخدمة الحقيقية للقاعدة لا تُلمس: `get_db` و`SessionLocal`
كلاهما موجَّه إلى المحرك المؤقت.
"""

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
    ("/faults-repairs", "الأعطال"),
    ("/faults-repairs/faults", None),
    ("/faults-repairs/repairs", None),
    ("/faults-repairs/analytics", None),
    ("/tires", "الإطارات"),
    ("/tires/inventory", None),
    ("/batteries", "البطاريات"),
    ("/fuel", "الوقود"),
    ("/missions", "المهمات"),
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
        "equipment": equipment.id,
        "fault": fault.id,
        "repair": repair.id,
    }


@pytest.fixture(scope="module")
def pages(request):
    """قاعدة مؤقتة + عميل مُصادَق. العزل مضمون على مستويين."""
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

        with TestClient(app) as client:
            response = client.post(
                "/login",
                data={"username": SEEDED_USERNAME, "password": SEEDED_PASSWORD},
                follow_redirects=False,
            )
            assert response.status_code in (302, 303), "فشل تسجيل الدخول"
            yield client, ids


def test_login_sets_a_session_that_authenticates_the_pages(pages):
    client, _ = pages
    assert client.cookies.get("fleet_session"), "لا كوكي جلسة بعد الدخول"


def test_pages_redirect_to_login_when_there_is_no_session():
    """كل صفحة محمية: بلا جلسة ⇒ 401/403 أو تحويل إلى /login — لا 200 ولا 500."""
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(main, "init_db", lambda: None)
        patch.setattr(main, "create_default_admin", lambda: None)
        with TestClient(main.create_app()) as client:
            for path, _ in PAGE_MARKERS:
                response = client.get(path, follow_redirects=False)
                assert response.status_code != 200, f"{path} متاحة بلا جلسة"
                assert response.status_code in (302, 303, 401, 403), (
                    f"{path} رجعت {response.status_code} بلا جلسة"
                )
                if response.status_code in (302, 303):
                    assert "/login" in response.headers.get("location", "")


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


def test_detail_pages_render(pages):
    """صفحات التفاصيل لم تكن مغطّاة إطلاقاً — أعطال/تصليح/عداد/تحرير عتاد."""
    client, ids = pages
    paths = [
        f"/equipment/{ids['equipment']}",
        f"/equipment/{ids['equipment']}/meters",
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


def test_fault_list_shows_spare_request_linked_through_repair(pages):
    client, _ = pages
    body = client.get("/faults-repairs/faults").text

    assert "SPR-PAGE-1" in body, "طلب الغيار المرتبط بالتصليح لا يظهر في سجل الأعطال"
    assert "حالة طلب الغيار" in body, "عمود حالة طلب الغيار غير موجود"
    assert "معلق" in body, "حالة طلب الغيار غير ظاهرة"


def test_fault_pages_show_arabic_status_and_severity(pages):
    """العطل المخزَّن `open`/`high` يجب ألا يظهر كمفتاح إنجليزي."""
    client, ids = pages
    body = client.get(f"/faults-repairs/faults/{ids['fault']}").text

    assert "مفتوح" in body, "حالة العطل غير مترجمة"
    assert "عالية" in body, "درجة الخطورة غير مترجمة"
    assert ">open<" not in body and ">high<" not in body
    assert "قيد الإصلاح" in body, "حالة التصليح غير مترجمة"
    assert ">in_progress<" not in body
