"""تعديل طلب الغيار داخل بياناته نفسها — والحفظ فعلياً في القاعدة.

الصفحة صارت تعرض حقول الطلب والبنود كحقول قابلة للتحرير داخل منطقة الطلب،
وزر «حفظ التعديلات» داخلها يرسل إلى الـ endpoints القائمة. هذا الملف
يمشي على المسار نفسه: يقرأ الصفحة، يضغط زر الحفظ، ثم يعيد القراءة من
قاعدة البيانات للتحقّق أن التعديلات وصلت فعلاً — لا أن الشاشة فقط تغيّرت.

يغطي أيضاً الاسم الحر لقطعة الغيار: البند قد يُحفظ باسم مكتوب يدوياً دون
ربط بالمخزون، و`spare_part_id` يبقى اختيارياً.
"""

import re
import shutil
import subprocess
import tempfile
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

    # عطل مستقل لكل اختبار: الطلب مرتبط بمصدره، ولا يُقبل أكثر من طلب غيار
    # واحد لكل عطل.
    spare_faults = []
    for n in range(8):
        extra = Fault(
            equipment_id=equipment.id,
            reported_date=date.today(),
            fault_type=f"عطل اختبار {n}",
            description="وصف",
            severity="low",
            status="open",
            exploitation_impact="limited",
            created_by_id=user.id,
        )
        db.add(extra)
        db.flush()
        spare_faults.append(extra.id)

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
        "fault": fault.id,
        "spare_faults": spare_faults,
        "request": request_obj.id,
        "item": request_obj.items[0].id,
    }


# --------------------------------------------------------------- الواجهة (HTML)


def test_the_page_has_no_edit_toolbar_at_the_top(client):
    """لا شريط أدوات تحرير في أعلى الصفحة، ولا أزرار تحرير داخل رأس الطلب."""
    page, _ = client
    html = page.get("/spare-parts-requests").text

    # الواجهة الجديدة لا تستخدم شريط التحرير العام؛ التحقق من غياب عناصره يكفي.
    assert "تعديل الطلب" not in html
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


def test_the_new_request_form_is_a_real_form_element(client):
    """The create-request container must be a <form>, not a <div>.

    A `submit` event is only dispatched by real <form> elements. When the
    container was a <div>, pressing "save request" did absolutely nothing:
    the listener never ran, no message appeared, nothing was logged, and the
    request was never created.
    """
    page, _ = client
    html = page.get("/spare-parts-requests").text

    opened = re.search(r"<(form|div)\b[^>]*\bid="requestForm"[^>]*>", html)
    assert opened, "no opening tag for #requestForm"
    assert opened.group(1) == "form", (
        "#requestForm must be a <form> so that its submit event can fire, "
        f"but it is a <{opened.group(1)}>"
    )
    # novalidate keeps our Arabic messages instead of the browser's tooltips
    assert "novalidate" in opened.group(0)
    assert html.count("<form") == html.count("</form>")


def test_the_save_request_button_is_inside_that_form(client):
    """The submit button must live between <form ...> and its </form>."""
    page, _ = client
    html = page.get("/spare-parts-requests").text

    open_at = re.search(r"<form\b[^>]*\bid=\"requestForm\"", html)
    close_at = html.index("</form>", open_at.end())
    button_at = html.index('id="saveRequest"')

    assert open_at.end() <= button_at < close_at, (
        "the save-request button is outside the form, so submitting cannot work"
    )
    tag = html[html.rindex("<button", open_at.end(), button_at): html.index(">", button_at)]
    assert 'type="submit"' in tag


def test_the_submit_listener_is_still_wired_to_the_form(client):
    page, _ = client
    html = page.get("/spare-parts-requests").text

    assert (
        "getElementById('requestForm').addEventListener('submit'" in html
    )
    # the handler must prevent the native navigation before posting to the API
    handler_at = html.index("getElementById('requestForm').addEventListener('submit'")
    assert "preventDefault" in html[handler_at : handler_at + 200]


def _row_source(html):
    return html[html.index("function row(x)") : html.index("function detailHtml")]


def test_the_request_row_still_carries_its_action_buttons(client):
    """Each request row must keep the buttons that open and delete it.

    Commit 89b8efe ("revert(ui): restore previous button actions") dropped the
    whole actions cell, so the "فتح" button and the "حذف الطلب" action-menu
    button stopped existing on the page.
    """
    page, _ = client
    html = page.get("/spare-parts-requests").text
    row = _row_source(html)

    assert "open-request" in row, "the open button is missing from the request row"
    assert "delete-request" in row, "the delete action is missing from the request row"
    assert 'class="status"' in row, "the status dropdown is missing from the request row"


def test_the_detail_row_gets_a_usable_id(client):
    """The detail row must expose a real id, otherwise it can never be opened.

    89b8efe emitted `<tr class="detail id="d123">`, which folds the id into the
    class attribute, so `getElementById('d'+id)` returned null: clicking a
    request did nothing and none of the in-place edit controls ever appeared.
    """
    page, _ = client
    html = page.get("/spare-parts-requests").text
    row = _row_source(html)

    assert 'class="detail" id="d' in row, (
        "the detail <tr> must be <tr class=\"detail\" id=\"d{id}\">, got a merged "
        "class/id attribute"
    )
    assert 'class="detail id=' not in row, "the class and id attributes got merged again"


def test_the_request_row_cells_match_the_table_headers(client):
    """The row must have exactly one cell per <th>, with no unclosed leftovers."""
    page, _ = client
    html = page.get("/spare-parts-requests").text
    row = _row_source(html)

    thead = html[html.index("<thead>") : html.index("</thead>")]
    columns = thead.count("<th>")
    assert columns == 8

    request_row = row[row.index('<tr class="request-row"') : row.index("</tr>")]
    detail_row = row[row.index('<tr class="detail"') :]

    assert request_row.count("<td") == request_row.count("</td>"), (
        "unbalanced <td> tags in the request row"
    )
    assert request_row.count("<td") == columns, (
        "the request row must render exactly one <td> per <th>"
    )
    assert "</td></td>" not in request_row, "there is a dangling </td> in the request row"
    assert request_row.count("<tr") == 1, "the row string must hold one <tr>"

    # the detail row spans the full width of the table
    span = re.search(r'<td colspan="(\d+)"', detail_row)
    assert span, "the detail row has no colspan"
    assert int(span.group(1)) == columns

    # and so does the "no requests" placeholder
    assert re.search(r'colspan="%d" class="empty"' % columns, html)


def test_server_error_messages_reach_the_page(client):
    """errText() must read a FastAPI error body, not just {msg: ...}.

    saveRequest() passes the whole response body to errText(). FastAPI answers
    {"detail": "..."}, so errText() found no .msg and returned the generic
    fallback: every server-side reason for a 400 stayed invisible and only the
    raw network line showed in the console.
    """
    page, _ = client
    html = page.get("/spare-parts-requests").text

    block = html[html.index("function errText") : html.index("const sourceType")]
    assert "d.detail" in block, (
        "errText() must unwrap the FastAPI 'detail' field, otherwise the "
        "server's Arabic message is replaced by the generic fallback"
    )

    # saveRequest() hands the body (not body.detail) to errText, so errText has
    # to cope with both shapes. Only the call sites matter here, not the
    # recursive call inside errText itself.
    call_sites = html.replace(block, "")
    assert "errText(d," in call_sites, "saveRequest should pass the parsed body"
    assert "errText(d.detail," not in call_sites, (
        "if the call sites pass body.detail then errText no longer needs to "
        "unwrap it; keep exactly one of the two styles"
    )


def test_a_received_item_is_not_resent_with_its_assignment(client):
    """A locked row must not carry spare_part_id / part_name / requested_quantity.

    itemRow() already disabled .i-part and .i-qty for a received item, but
    itemBody() kept reading their .value -- a disabled input still has one -- so
    every save re-sent the assignment and the server refused it with
    "لا يمكن تعديل التعيين أو الكمية المطلوبة بعد تسجيل الاستلام" (400).
    """
    page, _ = client
    html = page.get("/spare-parts-requests").text

    # the row advertises that it is locked
    assert 'data-locked="1"' in html, "itemRow must flag a locked row"
    assert "const locked=received>0||x.status!=='pending';" in html

    # the name field belongs to the same assignment, so it is locked too
    name_line = next(
        line for line in html.splitlines() if 'class="i-name" value=' in line
    )
    assert "+(locked?' disabled':'')" in name_line, (
        ".i-name must be disabled on a locked row, the server rejects a change there"
    )

    # and saveRequest drops those three keys instead of sending them
    assert (
        "delete body.spare_part_id;delete body.part_name;delete body.requested_quantity;"
        in html
    ), "a locked row must not re-send its assignment"
    assert "if(itemId&&p.tr.dataset.locked){" in html

    # a brand-new row is never locked, so it still sends everything
    add_line = html[html.index("function addLineRow") : html.index("function itemBody")]
    assert "data-locked" not in add_line
    assert "disabled" not in add_line


def test_the_locked_guard_stays_on_the_server(client):
    """Trimming the payload is a courtesy; the server keeps the authority."""
    services_src = (
        ROOT / "app" / "modules" / "spare_parts_requests" / "services.py"
    ).read_text(encoding="utf-8")

    assert "لا يمكن تعديل التعيين أو الكمية المطلوبة بعد تسجيل الاستلام" in services_src
    assert "if item.received_quantity > 0 and touches_assignment:" in services_src


def test_the_header_receipt_date_is_read_and_sent(client):
    """detailHtml() renders .f-rdate and the API accepts received_date.

    saveRequest() used to ignore the field entirely, so a receipt date typed in
    the request header was silently discarded.
    """
    page, _ = client
    html = page.get("/spare-parts-requests").text

    assert 'class="f-rdate"' in html, "the header receipt date field is missing"

    save = html[html.index("async function saveRequest") :]
    assert "host.querySelector('.f-rdate')" in save, (
        "saveRequest must read the header receipt date"
    )
    assert "const headerDate=head?head.value.trim():'';" in save, (
        "read it defensively: a null element used to crash the save"
    )
    assert "received_date:receipt||null" in save, (
        "the header receipt date must be sent to the API"
    )
    # one receipt date for the whole request: header and items must agree
    assert "dates[0]!==headerDate" in save

    schemas_src = (
        ROOT / "app" / "modules" / "spare_parts_requests" / "schemas.py"
    ).read_text(encoding="utf-8")
    assert "received_date" in schemas_src


# ------------------------------------------------- استلام خاطئ: يجب أن يكون قابلاً للتراجع


def _new_request(page, ids, number, slot=0):
    """طلب مستقل لكل اختبار، حتى لا تتداخل الحالة بينهم."""
    created = page.post(
        "/api/spare-parts-requests",
        json={
            "request_number": number,
            "request_date": date.today().isoformat(),
            "source_type": "fault",
            "source_id": ids["spare_faults"][slot],
            "items": [{"spare_part_id": ids["part"], "requested_quantity": 2}],
        },
    )
    assert created.status_code == 201, created.text
    return created.json()["id"], created.json()["items"][0]["id"]


def _record_receipt(page, item_id):
    return page.patch(
        f"/api/spare-parts-requests/items/{item_id}",
        json={
            "received_quantity": 1,
            "received_date": date.today().isoformat(),
            "recipient": "أمين المخزن",
            "supplier_institution": "مؤسسة الاختبار",
        },
    )


def test_a_null_received_quantity_is_refused_instead_of_crashing(client):
    """كان `received_quantity: null` يُسقط الخدمة بـ 500.

    الحقل يقبل None في المخطّط بينما العمود NOT NULL، فكانت المقارنة في
    update_item تقارن None بالعدد وتُنتج TypeError بدل ردّ مفهوم.
    """
    page, ids = client
    _, item_id = _new_request(page, ids, "SR-NULL-QTY", slot=0)

    response = page.patch(
        f"/api/spare-parts-requests/items/{item_id}",
        json={"received_quantity": None},
    )
    assert response.status_code == 422, (
        f"يجب أن يُرفض تفريغ الكمية برسالة مفهومة، لا أن ينهار الخادم: "
        f"{response.status_code} {response.text}"
    )


def test_a_mistaken_receipt_can_be_undone(client):
    """الاستلام الخاطئ كان يقفل الطلب للأبد: لا حذف ولا تصفير.

    التصفير مرفوض في المخطّط، و null كان ينهار، وتغيير الحالة إلى «ملغى» لا
    يفكّ الحارس لأنه ينظر إلى الكمية المستلمة لا إلى الحالة.
    """
    page, ids = client
    request_id, item_id = _new_request(page, ids, "SR-UNDO", slot=1)
    today = date.today().isoformat()

    assert _record_receipt(page, item_id).status_code == 200

    # بعد الاستلام: الحذف مرفوض، برسالة تشرح出路
    blocked = page.delete(f"/api/spare-parts-requests/{request_id}")
    assert blocked.status_code == 400
    assert "تراجع عن الاستلام" in blocked.text, (
        "رسالة رفض الحذف يجب أن تذكر التراجع عن الاستلام، وإلا بقي المستخدم "
        "بلا طريق: " + blocked.text
    )

    # التراجع عن الاستلام
    undone = page.delete(f"/api/spare-parts-requests/items/{item_id}/receipt")
    assert undone.status_code == 200, undone.text
    body = undone.json()
    assert float(body["received_quantity"]) == 0
    assert body["received_date"] is None
    assert body["recipient"] is None
    assert body["supplier_institution"] is None

    # البند خرج من سجل الاستلام
    register = page.get("/api/spare-parts-requests/received-register").json()
    assert not [r for r in register if r["request_number"] == "SR-UNDO"]

    # والبند صار قابلاً للتعديل، والحذف صار مفتوحاً
    edited = page.patch(
        f"/api/spare-parts-requests/items/{item_id}",
        json={"requested_quantity": 4, "part_name": "فلتر معدَّل"},
    )
    assert edited.status_code == 200, edited.text
    assert page.delete(f"/api/spare-parts-requests/{request_id}").status_code == 200


def test_the_shared_receipt_date_survives_until_the_last_receipt_is_undone(client):
    """تاريخ الاستلام واحد للطلب كله، فيبقى ما دام فيه بند مستلَم.

    البند الملغى يشارك بقية البنود التاريخ نفسه لأن التاريخ خاصية الطلب، لا
    البند. وما يهمّ أن يصحّح هو الترويسة: عندما يُلغى آخر استلام لا يبقى تاريخ
    بلا سند، وإلا ظلّ الطلب يعرض استلاماً بعد أن أُلغي كله.
    """
    page, ids = client
    request_id, first = _new_request(page, ids, "SR-STALE-DATE", slot=2)
    today = date.today().isoformat()

    # بند ثانٍ يبقى مستلماً، فتتحقق الحالة التي كشفها العيب
    added = page.post(
        f"/api/spare-parts-requests/{request_id}/items",
        json={"part_name": "بند ثانٍ", "requested_quantity": 1},
    )
    assert added.status_code == 201, added.text
    second = added.json()["id"]

    assert _record_receipt(page, first).status_code == 200
    assert _record_receipt(page, second).status_code == 200
    assert page.get(f"/api/spare-parts-requests/{request_id}").json()["received_date"] == today

    # التراجع عن بند واحد: يبقى التاريخ لمصالح البند الآخر
    assert page.delete(f"/api/spare-parts-requests/items/{first}/receipt").status_code == 200
    still = page.get(f"/api/spare-parts-requests/{request_id}").json()
    assert still["received_date"] == today, "التاريخ يبقى ما دام هناك بند مستلَم"
    by_id = {i["id"]: i for i in still["items"]}
    assert float(by_id[first]["received_quantity"]) == 0
    assert by_id[second]["received_date"] == today

    # التراجع عن آخر بند: يسقط التاريخ من الترويسة
    assert page.delete(f"/api/spare-parts-requests/items/{second}/receipt").status_code == 200
    cleared = page.get(f"/api/spare-parts-requests/{request_id}").json()
    assert cleared["received_date"] is None, (
        "لا يجوز أن يبقى تاريخ استلام بعد التراجع عن آخر استلام"
    )
    assert {i["received_date"] for i in cleared["items"]} == {None}


def test_undoing_a_receipt_twice_is_refused_not_crashed(client):
    page, ids = client
    _, item_id = _new_request(page, ids, "SR-UNDO-TWICE", slot=3)

    assert _record_receipt(page, item_id).status_code == 200
    assert page.delete(f"/api/spare-parts-requests/items/{item_id}/receipt").status_code == 200

    again = page.delete(f"/api/spare-parts-requests/items/{item_id}/receipt")
    assert again.status_code == 400, again.text
    assert "لا يوجد استلام" in again.text


def test_the_receipt_is_final_once_the_request_is_approved(client):
    """الاستلام واقعة موثّقة، فبعد القبول يصبح السجل نهائياً."""
    page, ids = client
    request_id, item_id = _new_request(page, ids, "SR-APPROVED-FINAL", slot=4)

    assert _record_receipt(page, item_id).status_code == 200
    approved = page.patch(
        f"/api/spare-parts-requests/{request_id}/status", json={"status": "approved"}
    )
    assert approved.status_code == 200, approved.text

    refused = page.delete(f"/api/spare-parts-requests/items/{item_id}/receipt")
    assert refused.status_code == 400, refused.text
    assert "قيد الانتظار" in refused.text


def test_the_undo_button_is_offered_only_while_the_request_is_pending(client):
    """التراجع يظهر على بندٍ مستلَم في طلب ما زال قيد الانتظار فقط."""
    page, _ = client
    html = page.get("/spare-parts-requests").text

    assert "const canUndo=received>0&&x.status==='pending';" in html, (
        "التراجع عن الاستلام مسموح ما دام الطلب قد يتغير"
    )
    assert html.count('class="secondary undo-receipt"') == 1, (
        "الزر يُرسم في خلية السطر المخزَّن فقط، لا في خلية الإضافة"
    )
    assert "await undoReceipt(ur.closest('tr'));" in html
    assert "/receipt'," in html, "الزر لا يستدعي مسار التراجع عن الاستلام"

    # والتأكيد يشرح أن السجل سيُحذف قبل التنفيذ
    assert "سيحذف البند من سجل الاستلام" in html


def test_the_router_declares_no_duplicate_endpoint(client):
    """كان `stats/pending-count` معرَّفاً مرتين بنفس اسم الدالة.

    التكرار لا يكسر الاستجابات، لكنه يخلط مواصفة OpenAPI: عملية واحدةٌ تحمل
    الاسم نفسه لمسارين، فيصدر تحذير Duplicate Operation ID، وتصبح أسماء
    العمليات في مولّدات العملاء غير فريدة.
    """
    from app.modules.spare_parts_requests.router import router

    seen: dict = {}
    for route in router.routes:
        for method in sorted(getattr(route, "methods", []) or []):
            key = (method, route.path)
            assert key not in seen, (
                f"{method} {route.path} معرّف مرتين: '{seen[key]}' و '{route.name}'"
            )
            seen[key] = route.name

    assert ("DELETE", "/api/spare-parts-requests/items/{item_id}/receipt") in seen, (
        "مسار التراجع عن الاستلام مفقود من الموجّه"
    )


def _render_item_row(node: str, item_js: str, context_js: str) -> str:
    """Run itemRow() in Node and return the HTML it produced."""
    template = TEMPLATE.read_text(encoding="utf-8")
    source = template[
        template.index("function itemRow") : template.index("function itemBody")
    ].strip()
    harness = (
        "const PARTS=[1];const PART_NAMES=['p'];const PART_NUMBERS=[''];\n"
        "const esc=s=>String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;');\n"
        + source
        + "\nprocess.stdout.write(itemRow("
        + item_js
        + ","
        + context_js
        + "));\n"
    )
    with tempfile.NamedTemporaryFile(
        "w", suffix=".js", encoding="utf-8", delete=False
    ) as handle:
        handle.write(harness)
        filename = handle.name
    try:
        done = subprocess.run(
            [node, filename], capture_output=True, text=True, encoding="utf-8"
        )
    finally:
        Path(filename).unlink(missing_ok=True)
    assert done.returncode == 0, f"itemRow() لم يعمل: {done.stderr}"
    return done.stdout


def test_the_item_name_field_is_a_well_formed_input(client):
    """itemRow() builds HTML by hand, so a stray quote goes unnoticed.

    Locking .i-name with `+(locked?' disabled':'')` once left an extra `"` in
    the string, and the row rendered as
    `<input class="i-name" ... placeholder="... *"">` -- a tag carrying a bogus
    attribute. The page still worked, so nothing caught it. Render the row and
    check the tag for real instead.
    """
    node = shutil.which("node")
    if not node:
        pytest.skip("node غير متوفر")

    item = "{id:1,part_name:'x',spare_part_id:1,requested_quantity:2,received_quantity:0}"
    expected = (
        r"""<input class="i-name" value="[^"]*" placeholder="[^"]*"( disabled)?>"""
    )

    for context, locked in (("{status:'pending'}", False), ("{status:'done'}", True)):
        markup = _render_item_row(node, item, context)
        tags = [t for t in re.findall(r"<input\b[^>]*>", markup) if "i-name" in t]
        assert len(tags) == 1, f"لم يُرسم حقل الاسم: {markup}"

        # every attribute spelled name="value": a loose quote would leave a
        # dangling one that this pattern cannot account for
        found = re.fullmatch(expected, tags[0])
        assert found, f"وسم حقل الاسم غير صالح: {tags[0]!r}"
        assert bool(found.group(1)) is locked, (
            "السطر المقفول يجب أن يكون للاسم معطّلاً، والسطر المفتوح غير معطّل"
        )


def test_a_duplicate_part_is_refused_before_sending(client):
    """The duplicate rule is checked in the page, with the server's own rule.

    Request 2 already held both library parts the dropdown offers, so every
    save produced another POST /items -> 400. The rule now runs before the
    round-trip and the Arabic message is shown instead.
    """
    page, _ = client
    html = page.get("/spare-parts-requests").text

    assert "const DUPLICATE_PART=" in html
    assert "const identityOf=tr=>" in html, "the identity helper is missing"
    assert "setMsg(DUPLICATE_PART,'err')" in html

    # the identity rule must match services._item_identity: library id when the
    # row is linked, otherwise the trimmed + casefolded free name
    helper = html[html.index("const identityOf=tr=>") : html.index("for(const p of payloads)")]
    assert "'id:'+pid" in helper
    assert ".toLowerCase()" in helper
    assert ".trim()" in helper

    # only brand-new rows are pre-checked; stored rows keep the server's verdict
    check = html[html.index("for(const p of payloads){") :]
    check = check[: check.index("try{")]
    assert "if(p.tr.dataset.itemId)continue;" in check


def test_the_received_register_survives_a_refused_duplicate(client):
    """The server still owns the rule; the page only avoids the wasted call."""
    page, _ = client
    html = page.get("/spare-parts-requests").text

    services_src = (
        ROOT / "app" / "modules" / "spare_parts_requests" / "services.py"
    ).read_text(encoding="utf-8")
    assert "قطعة الغيار موجودة بالفعل في الطلب" in services_src, (
        "the server-side duplicate guard must stay in place"
    )
    assert 'raise ValueError("اسم قطعة الغيار مطلوب")' in services_src