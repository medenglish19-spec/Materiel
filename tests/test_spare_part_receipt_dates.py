"""قواعد تاريخ الاستلام في طلبات قطع الغيار.

قاعدتان تربطان تاريخ الاستلام بتاريخ الطلب:

* ``received_date`` اختياري، لكن إن أُدخل فلا يسبق تاريخ الطلب.
* الطلب يُستلم مرة واحدة: تاريخ واحد على مستوى الطلب تتشاركه كل بنوده،
  وأي بند يحمل تاريخاً مختلفاً يُرفض برسالة توجيهية.

الاختبارات تمشي على الـ endpoints الفعلية على قاعدة في الذاكرة، فالتحقق
يُختبر كما يصله المستخدم لا كما يُكتب في المخطط.
"""

from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import model_registry  # noqa: F401  (يسجّل كل النماذج قبل create_all)
from app.database import session as session_module
from app.database.base import Base
from app.modules.spare_parts_requests import services
from web import main

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "app" / "modules" / "spare_parts_requests" / "templates" / "requests.html"

USERNAME = "receipt-date-keeper"
PASSWORD = "Test@12345"

REQUEST_DAY = date(2026, 3, 1)
BEFORE = REQUEST_DAY - timedelta(days=1)
AFTER = REQUEST_DAY + timedelta(days=9)


@pytest.fixture(scope="module")
def client():
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


@pytest.fixture(autouse=True)
def _no_receipt_yet(client):
    """كل اختبار يبدأ من طلب بلا تاريخ استلام، فلا يعتمد على ما قبله."""
    page, ids = client
    page.patch(f"/api/spare-parts-requests/{ids['request']}", json={"received_date": None})


def _seed(db):
    """مستخدم واحد وعتاد واحد وعطلان: الأول عليه طلب، والثاني留给 الإنشاء."""
    from app.core.security import hash_password
    from app.modules.equipment.models import Equipment
    from app.modules.equipment_types.models import EquipmentType
    from app.modules.faults_repairs.models import Fault
    from app.modules.spare_parts_requests.schemas import SparePartRequestCreate
    from app.modules.users.models import User

    user = User(
        username=USERNAME,
        full_name="أمين الاستلام",
        hashed_password=hash_password(PASSWORD),
        role="admin",
    )
    db.add(user)
    db.flush()

    eq_type = EquipmentType(name="شاحنات", measurement_unit="km")
    db.add(eq_type)
    db.flush()
    equipment = Equipment(
        asset_code="RD-1",
        registration_number="333-TEST",
        equipment_type_id=eq_type.id,
        technical_condition="ready",
        operational_status="available",
    )
    db.add(equipment)
    db.flush()

    def new_fault():
        fault = Fault(
            equipment_id=equipment.id,
            reported_date=REQUEST_DAY,
            fault_type="تعطل محرك",
            description="وصف",
            severity="high",
            status="open",
            exploitation_impact="limited",
            created_by_id=user.id,
        )
        db.add(fault)
        db.flush()
        return fault

    served = new_fault()
    free = new_fault()

    request_obj = services.create_request(
        db,
        SparePartRequestCreate(
            request_number="RD-1",
            request_date=REQUEST_DAY,
            source_type="fault",
            source_id=served.id,
            items=[{"part_name": "صمام تشغيل", "requested_quantity": 2}],
        ),
        user.id,
    )

    return {
        "number": "RD-1",
        "user": user.id,
        "equipment": equipment.id,
        "fault": served.id,
        "free_fault": free.id,
        "request": request_obj.id,
        "item": request_obj.items[0].id,
    }


def _reread(client, ids):
    return client.get(f"/api/spare-parts-requests/{ids['request']}").json()


def _set_request_receipt(client, ids, day):
    """ضبط تاريخ استلام الطلب من رأسه — الطريق الطبيعي بعد التغيير."""
    return client.patch(
        f"/api/spare-parts-requests/{ids['request']}",
        json={"received_date": day.isoformat() if day else None},
    )


def _record_item(client, ids, day, **extra):
    body = {
        "received_quantity": 1,
        "received_date": day.isoformat() if day else None,
        "recipient": "أمين المخزن",
        "supplier_institution": "مؤسسة الاختبار",
    }
    body.update(extra)
    return client.patch(f"/api/spare-parts-requests/items/{ids['item']}", json=body)


# ------------------------------------------------- تاريخ الاستلام >= تاريخ الطلب


class TestReceiptNotBeforeRequest:
    def test_receipt_before_request_is_refused(self, client):
        page, ids = client

        response = _record_item(page, ids, BEFORE)

        assert response.status_code == 400, response.text
        assert "لا يمكن أن يكون قبل تاريخ الطلب" in response.text

    def test_a_refused_date_is_not_stored(self, client):
        page, ids = client
        _record_item(page, ids, REQUEST_DAY - timedelta(days=3))

        reread = _reread(page, ids)
        assert reread["received_date"] is None
        assert reread["items"][0]["received_date"] is None

    def test_the_same_day_is_accepted(self, client):
        """التاريخ المساوي لتاريخ الطلب ليس «قبله»."""
        page, ids = client

        response = _record_item(page, ids, REQUEST_DAY)

        assert response.status_code == 200, response.text
        assert _reread(page, ids)["received_date"] == REQUEST_DAY.isoformat()

    def test_a_later_date_is_accepted(self, client):
        page, ids = client

        assert _record_item(page, ids, AFTER).status_code == 200
        assert _reread(page, ids)["received_date"] == AFTER.isoformat()

    def test_the_date_is_optional(self, client):
        """قد لا تكون القطعة قد استُلمت بعد: غياب التاريخ ليس خطأ."""
        page, ids = client

        response = _set_request_receipt(page, ids, None)

        assert response.status_code == 200, response.text
        assert _reread(page, ids)["received_date"] is None

    def test_the_rule_is_a_single_comparison(self, client):
        """القاعدة نفسها تستدعيها الواجهة والخدمة، فهي واحدة لا نسختان."""
        assert services.RECEIPT_BEFORE_REQUEST in TEMPLATE.read_text(encoding="utf-8")

    def test_moving_the_request_date_after_its_receipt_is_refused(self, client):
        """تعديل تاريخ الطلب إلى ما بعد تاريخ الاستلام مرفوض، ويبقى التاريخ."""
        page, ids = client
        _set_request_receipt(page, ids, AFTER)

        response = page.patch(
            f"/api/spare-parts-requests/{ids['request']}",
            json={"request_date": (AFTER + timedelta(days=5)).isoformat()},
        )

        assert response.status_code == 400, response.text
        assert _reread(page, ids)["received_date"] == AFTER.isoformat()

    def test_the_service_refuses_a_receipt_before_the_request_date(self):
        """خط الدفاع الثاني: الحركة في تاريخ الطلب نفسه."""
        with pytest.raises(ValueError, match="قبل تاريخ الطلب"):
            services._check_receipt_date(AFTER, REQUEST_DAY)
        # التاريخ المساوي أو اللاحق مقبول، وغيابه اختياري
        assert services._check_receipt_date(REQUEST_DAY, REQUEST_DAY) is None
        assert services._check_receipt_date(REQUEST_DAY, None) is None


# --------------------------------------------------- تاريخ استلام واحد للطلب


class TestSingleReceiptDatePerRequest:
    def test_the_receipt_lives_on_the_request_and_is_shared_by_items(self, client):
        page, ids = client
        _set_request_receipt(page, ids, AFTER)

        added = page.post(
            f"/api/spare-parts-requests/{ids['request']}/items",
            json={"part_name": "طرمبة زيت", "requested_quantity": 1},
        )
        assert added.status_code == 201, added.text

        reread = _reread(page, ids)
        assert reread["received_date"] == AFTER.isoformat()
        assert {i["received_date"] for i in reread["items"]} == {AFTER.isoformat()}

    def test_an_item_with_the_same_date_is_accepted(self, client):
        page, ids = client
        _set_request_receipt(page, ids, AFTER)

        response = page.post(
            f"/api/spare-parts-requests/{ids['request']}/items",
            json={
                "part_name": "طرمبة مياه",
                "requested_quantity": 1,
                "received_date": AFTER.isoformat(),
            },
        )

        assert response.status_code == 201, response.text

    def test_an_item_with_another_date_is_refused_with_a_guidance(self, client):
        page, ids = client
        _set_request_receipt(page, ids, AFTER)

        response = page.post(
            f"/api/spare-parts-requests/{ids['request']}/items",
            json={
                "part_name": "مسامير عيار",
                "requested_quantity": 1,
                "received_date": (AFTER + timedelta(days=2)).isoformat(),
            },
        )

        assert response.status_code == 400, response.text
        assert "له تاريخ استلام واحد" in response.text
        assert "افتح طلب غيار جديد" in response.text

    def test_editing_an_item_to_another_date_is_refused(self, client):
        page, ids = client
        _set_request_receipt(page, ids, AFTER)

        response = _record_item(page, ids, AFTER + timedelta(days=5))

        assert response.status_code == 400, response.text
        assert "افتح طلب غيار جديد" in response.text

    def test_changing_the_request_date_moves_every_item(self, client):
        """التعديل مسموح على رأس الطلب وينتقل لكل بنوده."""
        page, ids = client
        _set_request_receipt(page, ids, AFTER)
        new_day = REQUEST_DAY + timedelta(days=20)

        response = _set_request_receipt(page, ids, new_day)

        assert response.status_code == 200, response.text
        reread = _reread(page, ids)
        assert reread["received_date"] == new_day.isoformat()
        assert {i["received_date"] for i in reread["items"]} == {new_day.isoformat()}

    def test_an_unrelated_edit_does_not_clear_the_receipt(self, client):
        page, ids = client
        _set_request_receipt(page, ids, AFTER)

        response = page.patch(
            f"/api/spare-parts-requests/items/{ids['item']}",
            json={"notes": "ملاحظة جديدة"},
        )

        assert response.status_code == 200, response.text
        assert _reread(page, ids)["received_date"] == AFTER.isoformat()

    def test_the_register_shows_one_date_per_request(self, client):
        page, ids = client
        _set_request_receipt(page, ids, AFTER)

        rows = page.get("/api/spare-parts-requests/received-register").json()
        mine = [r for r in rows if r["request_number"] == ids["number"]]

        assert mine, "سجل المستلم يجب أن يعرض بنود الطلب المستلمة"
        assert {r["received_date"] for r in mine} == {AFTER.isoformat()}


# -------------------------------------------------------------------- الإنشاء


class TestCreateRequest:
    def test_creating_with_a_receipt_before_the_request_is_refused(self, client):
        page, ids = client

        response = page.post(
            "/api/spare-parts-requests",
            json={
                "request_number": "RD-90",
                "request_date": REQUEST_DAY.isoformat(),
                "received_date": BEFORE.isoformat(),
                "source_type": "fault",
                "source_id": ids["free_fault"],
                "items": [{"part_name": "قطعة جافة", "requested_quantity": 1}],
            },
        )

        assert response.status_code == 400, response.text
        assert "لا يمكن أن يكون قبل تاريخ الطلب" in response.text

    def test_creating_without_a_receipt_is_allowed(self, client):
        page, ids = client

        response = page.post(
            "/api/spare-parts-requests",
            json={
                "request_number": "RD-91",
                "request_date": REQUEST_DAY.isoformat(),
                "source_type": "fault",
                "source_id": ids["free_fault"],
                "items": [{"part_name": "قطعة ثانية", "requested_quantity": 1}],
            },
        )

        assert response.status_code == 201, response.text
        assert response.json()["received_date"] is None


# ------------------------------------------------------------------- الواجهة


def test_the_page_exposes_one_receipt_date_in_the_request_header(client):
    page, _ = client
    html = page.get("/spare-parts-requests").text

    assert 'class="f-rdate" type="date"' in html
    detail_block = html[html.index("function detailHtml"):html.index("function itemsHtml")]
    assert "تاريخ الاستلام" in detail_block


def test_the_page_blocks_both_rules_before_sending_anything(client):
    page, _ = client
    html = page.get("/spare-parts-requests").text
    block = html[
        html.index("async function saveRequest"):html.index(
            "document.getElementById('rows').addEventListener('click'"
        )
    ]

    assert "RECEIPT_CONFLICT" in block, "الصفحة لا ترفض اختلاف تواريخ الاستلام بين البنود"
    assert "RECEIPT_BEFORE_REQUEST" in block, "الصفحة لا ترفض تاريخ استلام قبل تاريخ الطلب"
    # القاعدة تُفحص قبل أول طلب إلى الخادم
    assert block.index("RECEIPT_CONFLICT") < block.index("fetch('/api/spare-parts-requests/'+id")
