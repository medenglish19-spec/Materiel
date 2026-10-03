"""تعديل طلب الغيار داخل بياناته نفسها — والحفظ فعلياً في القاعدة.

الصفحة صارت تعرض حقول الطلب والبنود كحقول قابلة للتحرير داخل منطقة الطلب،
وزر «حفظ التعديلات» داخلها يرسل إلى الـ endpoints القائمة. هذا الملف
يمشي على المسار نفسه: يقرأ الصفحة، يضغط زر الحفظ، ثم يعيد القراءة من
قاعدة البيانات للتحقّق أن التعديلات وصلت فعلاً — لا أن الشاشة فقط تغيّرت.

يغطي أيضاً الاسم الحر لقطعة الغيار: البند قد يُحفظ باسم مكتوب يدوياً دون
ربط بالمخزون، و`spare_part_id` يبقى اختيارياً.
"""

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import model_registry  # noqa: F401  (يسجّل كل النماذج قبل create_all)
from app.database import session as session_module
from app.database.base import Base
from web import main

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = (
    ROOT / "app" / "modules" / "spare_parts_requests" / "templates" / "requests.html"
)

USERNAME = "spare-parts-editor"
PASSWORD = "Test@12345"


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


def _seed(db):
    from app.core.security import hash_password
    from app.modules.equipment.models import Equipment
    from app.modules.equipment_types.models import EquipmentModel, EquipmentType
    from app.modules.faults_repairs.models import Fault, SparePart
    from app.modules.spare_parts_requests import services
    from app.modules.spare_parts_requests.schemas import SparePartRequestCreate
    from app.modules.users.models import User

    user = User(
        username=USERNAME,
        full_name="محرر طلبات الغيار",
        hashed_password=hash_password(PASSWORD),
        role="admin",
    )
    db.add(user)
    db.flush()

    eq_type = EquipmentType(name="شاحنات", measurement_unit="km")
    db.add(eq_type)
    db.flush()
    model = EquipmentModel(name="طراز اختبار", equipment_type_id=eq_type.id)
    db.add(model)
    db.flush()
    equipment = Equipment(
        asset_code="SP-1",
        registration_number="222-TEST",
        equipment_type_id=eq_type.id,
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
        description="وصف",
        severity="high",
        status="open",
        exploitation_impact="limited",
        created_by_id=user.id,
    )
    db.add(fault)
    db.flush()

    part = SparePart(name="فلتر هوائي", part_number="F-1", receiving_document="وثيقة استلام")
    db.add(part)
    db.flush()

    request_obj = services.create_request(
        db,
        SparePartRequestCreate(
            request_number="SR-EDIT-1",
            request_date=date.today(),
            source_type="fault",
            source_id=fault.id,
            notes="ملاحظة أولية",
            items=[{"part_name": "قطعة حرة واحدة", "requested_quantity": 2}],
        ),
        user.id,
    )

    return {
        "user": user.id,
        "part": part.id,
        "request": request_obj.id,
        "item": request_obj.items[0].id,
    }


# --------------------------------------------------------------- الواجهة (HTML)


def test_the_page_has_no_edit_toolbar_at_the_top(client):
    """لا شريط أدوات تحرير في أعلى الصفحة، ولا أزرار تحرير داخل رأس الطلب."""
    page, _ = client
    html = page.get("/spare-parts-requests").text

    # شريط الأدوات العام مخفي على هذه الصفحة
    assert ".app-workbar{display:none}" in html
    # لا أدوات تحرير داخل الطلب نفسه
    assert "تعديل الطلب" not in html
    assert 'class="detail-actions"' not in html


def test_the_save_button_lives_inside_the_request_area(client):
    page, _ = client
    html = page.get("/spare-parts-requests").text

    assert "حفظ التعديلات" in html
    # الزر يُبنى داخل منطقة الطلب (detailHtml) لا في أعلى الصفحة
    assert '"save-request"' in html
    detail_block = html[html.index("function detailHtml"):html.index("function itemsHtml")]
    assert "حفظ التعديلات" in detail_block
    assert "حفظ التعديلات" not in html[: html.index("function detailHtml")]


def test_header_fields_and_items_are_editable_in_place(client):
    page, _ = client
    html = page.get("/spare-parts-requests").text

    for cls in (
        "f-number",
        "f-date",
        "f-notes",
        "i-name",
        "i-part",
        "i-qty",
        "received",
        "i-rdate",
        "i-recipient",
        "i-supplier",
        "i-note",
        "add-line",
        "rm-line",
    ):
        assert cls in html, f"الحقل أو الأداة {cls} غير موجود"
    # لم يعد التعديل عبر نوافذ prompt
    assert "prompt(" not in html


def test_the_global_editor_does_not_manage_this_area(client):
    """منطقة الطلب تُحفظ بزرها الخاص، لا بمحرِّر الصفحة العام."""
    page, _ = client
    html = page.get("/spare-parts-requests").text
    assert "data-em-ignore" in html


def test_received_quantity_input_refuses_zero_in_the_browser(client):
    page, _ = client
    html = page.get("/spare-parts-requests").text
    assert 'class="received" type="number" min="1" step="1"' in html


# ------------------------------------------------------------- الحفظ فعلياً


def test_editing_a_free_text_part_name_is_persisted(client):
    """تعديل اسم البند الحر يُحفظ في القاعدة ويُعاد بعد إعادة الفتح."""
    page, ids = client
    item_id = ids["item"]

    response = page.patch(
        f"/api/spare-parts-requests/items/{item_id}",
        json={"part_name": "اسم حر بعد التعديل", "requested_quantity": 5},
    )
    assert response.status_code == 200, response.text

    reread = page.get(f"/api/spare-parts-requests/{ids['request']}").json()
    item = reread["items"][0]
    assert item["part_name"] == "اسم حر بعد التعديل"
    assert str(item["requested_quantity"]).rstrip("0").rstrip(".") == "5"
    assert item["spare_part_id"] is None, "بند حر يجب أن يبقى بلا ربط بالمخزون"


def test_adding_an_item_with_a_free_text_name_is_persisted(client):
    page, ids = client

    response = page.post(
        f"/api/spare-parts-requests/{ids['request']}/items",
        json={"part_name": "بند مضاف بحر", "requested_quantity": 3},
    )
    assert response.status_code == 201, response.text
    new_id = response.json()["id"]

    reread = page.get(f"/api/spare-parts-requests/{ids['request']}").json()
    names = [i["part_name"] for i in reread["items"]]
    assert "بند مضاف بحر" in names
    assert len(reread["items"]) == 2

    # حذف البند الجديد والتأكد أنه زال فعلاً
    assert page.delete(f"/api/spare-parts-requests/items/{new_id}").status_code == 200
    after = page.get(f"/api/spare-parts-requests/{ids['request']}").json()
    assert [i["id"] for i in after["items"]] == [ids["item"]]


def test_selecting_a_library_part_stores_the_link_and_keeps_the_typed_name(client):
    """الاسم حر، لكن الربط بالمخزون اختياري ويحفظ الاسم المكتوب."""
    page, ids = client

    response = page.patch(
        f"/api/spare-parts-requests/items/{ids['item']}",
        json={"part_name": "فلتر هوائي - ماركة خاصة", "spare_part_id": ids["part"], "requested_quantity": 4},
    )
    assert response.status_code == 200, response.text

    reread = page.get(f"/api/spare-parts-requests/{ids['request']}").json()
    item = reread["items"][0]
    assert item["spare_part_id"] == ids["part"]
    assert item["part_name"] == "فلتر هوائي - ماركة خاصة"


def test_clearing_the_library_link_keeps_the_free_name(client):
    page, ids = client

    response = page.patch(
        f"/api/spare-parts-requests/items/{ids['item']}",
        json={"spare_part_id": None},
    )
    assert response.status_code == 200, response.text

    item = page.get(f"/api/spare-parts-requests/{ids['request']}").json()["items"][0]
    assert item["spare_part_id"] is None
    assert item["part_name"], "الاسم الحر يجب أن يبقى محفوظاً بعد فك الربط"


def test_duplicate_free_text_names_in_one_request_are_rejected(client):
    page, ids = client

    response = page.post(
        f"/api/spare-parts-requests/{ids['request']}/items",
        json={"part_name": item_name(page, ids), "requested_quantity": 1},
    )
    assert response.status_code == 400
    assert "موجودة بالفعل" in response.text


def item_name(page, ids):
    return page.get(f"/api/spare-parts-requests/{ids['request']}").json()["items"][0]["part_name"]


def test_an_item_without_any_name_is_rejected(client):
    page, ids = client

    response = page.post(
        f"/api/spare-parts-requests/{ids['request']}/items",
        json={"requested_quantity": 1},
    )
    # schema validation rejects before reaching service
    assert response.status_code == 422


def test_request_header_edits_are_persisted(client):
    page, ids = client
    today = date.today().isoformat()

    response = page.patch(
        f"/api/spare-parts-requests/{ids['request']}",
        json={"request_number": "SR-EDIT-2", "request_date": today, "notes": "ملاحظة معدلة"},
    )
    assert response.status_code == 200, response.text

    reread = page.get(f"/api/spare-parts-requests/{ids['request']}").json()
    assert reread["request_number"] == "SR-EDIT-2"
    assert reread["notes"] == "ملاحظة معدلة"


def test_receiving_data_is_editable_and_lands_in_the_register(client):
    """بيانات الاستلام تُحفظ من داخل الطلب وتظهر في سجل المستلم."""
    page, ids = client
    today = date.today().isoformat()

    response = page.patch(
        f"/api/spare-parts-requests/items/{ids['item']}",
        json={
            "received_quantity": 2,
            "received_date": today,
            "recipient": "أمين المخزن",
            "supplier_institution": "مؤسسة الاختبار",
        },
    )
    assert response.status_code == 200, response.text

    register = page.get("/api/spare-parts-requests/received-register").json()
    rows = [r for r in register if r["request_number"] == "SR-EDIT-2"]
    assert rows, "البند المستلم لم يظهر في سجل المستلم"
    assert rows[0]["recipient"] == "أمين المخزن"
    assert rows[0]["supplier_institution"] == "مؤسسة الاختبار"
    assert rows[0]["part_name"], "سجل المستلم يجب أن يعرض اسم البند الحر"


def test_an_empty_receipt_is_refused(client):
    """صفر ليس استلاماً: الكمية المستلمة إما مُتروكة (0) أو 1 فأكثر."""
    page, ids = client

    response = page.patch(
        f"/api/spare-parts-requests/items/{ids['item']}",
        json={"received_quantity": 0},
    )
    assert response.status_code == 422, response.text


def test_a_received_item_cannot_be_deleted(client):
    page, ids = client

    response = page.delete(f"/api/spare-parts-requests/items/{ids['item']}")
    assert response.status_code == 400
    assert "تم تسجيل استلام" in response.text


def test_the_whole_page_still_renders_for_a_logged_in_user(client):
    page, _ = client
    for path in ("/spare-parts-requests", "/spare-parts-received"):
        response = page.get(path)
        assert response.status_code == 200, f"{path} رجعت {response.status_code}"
        assert "Traceback" not in response.text