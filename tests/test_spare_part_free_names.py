"""اسم قطعة الغيار في طلب الغيار: نص حرّ، وربط اختياري بالمكتبة.

قبل هذا الملف كان حقل القطعة قائمة منسدلة إجبارية مربوطة بـ `spare_parts.id`،
فلا يمكن طلب قطعة غير موجودة في المكتبة إطلاقاً. الآن:

* الاسم نص حرّ: يُكتب ولا يحتاج قطعة في المكتبة.
* الربط اختياري: إن وافق الاسم قطعة واحدة من المكتبة رُبط البند بها.
* `spare_part_id` صار اختيارياً في النموذج، وبقي منطق المكتبة كما هو.

كل الاختبارات هنا على قاعدة مؤقتة في الذاكرة: `fleet_assets.db` لا تُلمَس.
"""

from datetime import date

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import model_registry  # noqa: F401  (يسجّل كل النماذج قبل create_all)
from app.database.base import Base
from app.modules.faults_repairs.models import Fault, SparePart
from app.modules.spare_parts_requests import services
from app.modules.spare_parts_requests.models import SparePartRequestItem
from app.modules.spare_parts_requests.schemas import (
    SparePartRequestCreate,
    SparePartRequestItemCreate,
    SparePartRequestItemUpdate,
)


# --------------------------------------------------------------------- الإعداد

@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _part(db, name, number):
    part = SparePart(name=name, part_number=number, receiving_document="DOC-" + number)
    db.add(part)
    db.commit()
    db.refresh(part)
    return part


def _fault(db):
    """عطل واحد على عتاد واحد: المصدر الوحيد الذي يقبله طلب الغيار."""
    from app.modules.equipment.models import Equipment
    from app.modules.equipment_types.models import EquipmentType

    equipment_type = EquipmentType(name="شاحنات اختبار", measurement_unit="km")
    db.add(equipment_type)
    db.flush()
    equipment = Equipment(
        asset_code="SP-TEST",
        registration_number="999-TEST",
        equipment_type_id=equipment_type.id,
        technical_condition="ready",
        operational_status="available",
    )
    db.add(equipment)
    db.flush()
    fault = Fault(
        equipment_id=equipment.id,
        reported_date=date(2026, 3, 1),
        fault_type="تعطل محرك",
        description="وصف",
        severity="high",
        status="open",
        exploitation_impact="limited",
    )
    db.add(fault)
    db.commit()
    db.refresh(fault)
    return fault


def _request(db, fault, number, items):
    """`create_request` يُرجع كائن ORM؛ التحويل إلى قاموس يجعل التأكيدات مقروءة."""
    return services.serialize_request(services.create_request(
        db,
        SparePartRequestCreate(
            request_number=number,
            request_date=fault.reported_date,
            source_type="fault",
            source_id=fault.id,
            items=items,
        ),
    ))


def _items_of(db, request_id):
    return services.serialize_request(services.get_request(db, request_id))["items"]


def _first_item(db, request_id):
    return services.get_request(db, request_id).items[0]


# ------------------------------------------------------------------ الـ schema

class TestItemSchema:
    def test_library_part_id_still_accepted(self):
        """التوافق: الطلب القديم بمعرّف قطعة يجب أن يبقى صالحاً."""
        item = SparePartRequestItemCreate(spare_part_id=1, requested_quantity=2)
        assert item.spare_part_id == 1
        assert item.spare_part_name is None

    def test_free_name_accepted_without_id(self):
        item = SparePartRequestItemCreate(spare_part_name="جسر مشغول", requested_quantity=3)
        assert item.spare_part_id is None
        assert item.spare_part_name == "جسر مشغول"

    def test_name_is_trimmed(self):
        item = SparePartRequestItemCreate(spare_part_name="  مرشح هوائي  ", requested_quantity=1)
        assert item.spare_part_name == "مرشح هوائي"

    def test_neither_id_nor_name_is_rejected(self):
        with pytest.raises(ValidationError):
            SparePartRequestItemCreate(requested_quantity=1)

    def test_blank_name_without_id_is_rejected(self):
        with pytest.raises(ValidationError):
            SparePartRequestItemCreate(spare_part_name="   ", requested_quantity=1)

    def test_receipt_fields_still_optional_and_intact(self):
        item = SparePartRequestItemCreate(
            spare_part_name="كابل نحاسي",
            requested_quantity=4,
            received_quantity=2,
            received_date=date(2026, 3, 5),
            recipient="أمين المخزن",
            supplier_institution="مؤسسة الواردات",
            notes="وصلت ناقصة",
        )
        assert (item.received_quantity, item.received_date) == (2, date(2026, 3, 5))
        assert item.recipient == "أمين المخزن"
        assert item.supplier_institution == "مؤسسة الواردات"
        assert item.notes == "وصلت ناقصة"


# -------------------------------------------------------------------- النموذج

def test_item_part_id_is_optional_column():
    column = SparePartRequestItem.__table__.columns["spare_part_id"]
    assert column.nullable is True
    assert "spare_part_name" in SparePartRequestItem.__table__.columns
    assert SparePartRequestItem.__table__.columns["spare_part_name"].nullable is True


# ------------------------------------------------------------------- الربط

class TestResolvePart:
    def test_known_id_is_bound(self, db):
        part = _part(db, "رديتر مشعّ", "SP-10")
        assert services.resolve_part(db, part.id, "أي اسم") == (part.id, None)

    def test_unknown_id_is_rejected(self, db):
        with pytest.raises(ValueError):
            services.resolve_part(db, 9999, None)

    def test_name_matching_one_library_part_is_bound(self, db):
        part = _part(db, "رديتر مشعّ", "SP-11")
        assert services.resolve_part(db, None, "رديتر مشعّ") == (part.id, None)

    def test_name_absent_from_library_stays_free(self, db):
        _part(db, "رديتر مشعّ", "SP-12")
        assert services.resolve_part(db, None, "صمام غير موجود بالمكتبة") == (None, "صمام غير موجود بالمكتبة")

    def test_ambiguous_name_stays_free_instead_of_guessing(self, db):
        """اسم واحد يطابق قطعتين: الربط العشوائي خطأ، فيبقى الاسم حراً."""
        _part(db, "وردة", "SP-13")
        _part(db, "وردة", "SP-14")
        assert services.resolve_part(db, None, "وردة") == (None, "وردة")

    def test_empty_reference_is_rejected(self, db):
        with pytest.raises(ValueError):
            services.resolve_part(db, None, None)


# -------------------------------------------------------------- الطلب كاملاً

class TestCreateRequest:
    def test_library_item_and_free_item_together(self, db):
        fault = _fault(db)
        part = _part(db, "رديتر مشعّ", "SP-20")
        created = _request(db, fault, "SP/26/001", [
            SparePartRequestItemCreate(spare_part_id=part.id, requested_quantity=2),
            SparePartRequestItemCreate(spare_part_name="مفتاح مشغول", requested_quantity=5),
        ])
        items = {i["part_name"]: i for i in created["items"]}
        assert items["رديتر مشعّ"]["spare_part_id"] == part.id
        assert items["رديتر مشعّ"]["spare_part_name"] is None
        assert items["مفتاح مشغول"]["spare_part_id"] is None
        assert items["مفتاح مشغول"]["spare_part_name"] == "مفتاح مشغول"
        assert items["مفتاح مشغول"]["requested_quantity"] == 5

    def test_typed_library_name_is_bound_automatically(self, db):
        """مطابقة الاسم بالمكتبة تكفي للربط، تماماً كما يفعل النموذج في المتصفح."""
        part = _part(db, "خرطوم وقود", "SP-21")
        fault = _fault(db)
        created = _request(db, fault, "SP/26/002", [
            SparePartRequestItemCreate(spare_part_name="خرطوم وقود", requested_quantity=1),
        ])
        assert created["items"][0]["spare_part_id"] == part.id
        assert created["items"][0]["part_name"] == "خرطوم وقود"

    def test_duplicate_free_name_rejected(self, db):
        fault = _fault(db)
        with pytest.raises(ValueError):
            _request(db, fault, "SP/26/003", [
                SparePartRequestItemCreate(spare_part_name="مفتاح مشغول", requested_quantity=1),
                SparePartRequestItemCreate(spare_part_name="مفتاح مشغول", requested_quantity=2),
            ])

    def test_duplicate_library_part_rejected(self, db):
        part = _part(db, "رديتر مشعّ", "SP-22")
        fault = _fault(db)
        with pytest.raises(ValueError):
            _request(db, fault, "SP/26/004", [
                SparePartRequestItemCreate(spare_part_id=part.id, requested_quantity=1),
                SparePartRequestItemCreate(spare_part_id=part.id, requested_quantity=2),
            ])


class TestAddAndEditItem:
    def test_add_free_item_to_existing_request(self, db):
        fault = _fault(db)
        part = _part(db, "رديتر مشعّ", "SP-30")
        created = _request(db, fault, "SP/26/010", [
            SparePartRequestItemCreate(spare_part_id=part.id, requested_quantity=1),
        ])
        services.add_item(db, created["id"], SparePartRequestItemCreate(
            spare_part_name="كابل نحاسي", requested_quantity=7, notes="طويل",
        ))
        items = {i["part_name"]: i for i in _items_of(db, created["id"])}
        assert items["كابل نحاسي"]["requested_quantity"] == 7
        assert items["كابل نحاسي"]["notes"] == "طويل"

    def test_add_same_free_name_twice_is_rejected(self, db):
        fault = _fault(db)
        created = _request(db, fault, "SP/26/011", [
            SparePartRequestItemCreate(spare_part_name="كابل نحاسي", requested_quantity=1),
        ])
        with pytest.raises(ValueError):
            services.add_item(db, created["id"], SparePartRequestItemCreate(
                spare_part_name="كابل نحاسي", requested_quantity=2,
            ))

    def test_receiving_needs_full_receipt_data(self, db):
        fault = _fault(db)
        created = _request(db, fault, "SP/26/012", [
            SparePartRequestItemCreate(spare_part_name="كابل نحاسي", requested_quantity=4),
        ])
        with pytest.raises(ValueError):
            services.add_item(db, created["id"], SparePartRequestItemCreate(
                spare_part_name="كابل نحاسي مرفوض", requested_quantity=1, received_quantity=2,
            ))
        item = services.add_item(db, created["id"], SparePartRequestItemCreate(
            spare_part_name="مروحة تبريد", requested_quantity=4, received_quantity=2,
            received_date=date(2026, 3, 6), recipient="أمين المخزن",
            supplier_institution="مؤسسة الواردات",
        ))
        assert item.received_quantity == 2
        assert item.spare_part_id is None
        assert item.spare_part_name == "مروحة تبريد"

    def test_rename_free_item(self, db):
        fault = _fault(db)
        created = _request(db, fault, "SP/26/013", [
            SparePartRequestItemCreate(spare_part_name="اسم قديم", requested_quantity=2),
        ])
        updated = services.update_item(
            db, _first_item(db, created["id"]),
            SparePartRequestItemUpdate(spare_part_name="اسم جديد"),
        )
        assert updated.spare_part_name == "اسم جديد"
        assert updated.spare_part_id is None

    def test_free_name_becomes_library_link_when_it_matches(self, db):
        part = _part(db, "بلبر صمام", "SP-31")
        fault = _fault(db)
        created = _request(db, fault, "SP/26/014", [
            SparePartRequestItemCreate(spare_part_name="اسم مؤقت", requested_quantity=2),
        ])
        updated = services.update_item(
            db, _first_item(db, created["id"]),
            SparePartRequestItemUpdate(spare_part_name="بلبر صمام"),
        )
        assert updated.spare_part_id == part.id
        assert updated.spare_part_name is None
        assert services.serialize_item(updated)["part_name"] == "بلبر صمام"

    def test_cannot_rename_to_a_name_already_in_the_request(self, db):
        fault = _fault(db)
        created = _request(db, fault, "SP/26/015", [
            SparePartRequestItemCreate(spare_part_name="بلبر أ", requested_quantity=1),
            SparePartRequestItemCreate(spare_part_name="بلبر ب", requested_quantity=1),
        ])
        second = next(
            i for i in services.get_request(db, created["id"]).items
            if i.spare_part_name == "بلبر ب"
        )
        with pytest.raises(ValueError):
            services.update_item(db, second, SparePartRequestItemUpdate(spare_part_name="بلبر أ"))

    def test_renaming_an_item_to_its_own_name_is_allowed(self, db):
        """البند مستثنى من فحص التكرار: إعادة كتابة اسمه بنفسه ليست تكراراً."""
        fault = _fault(db)
        created = _request(db, fault, "SP/26/018", [
            SparePartRequestItemCreate(spare_part_name="بلبر ج", requested_quantity=1),
        ])
        updated = services.update_item(
            db, _first_item(db, created["id"]),
            SparePartRequestItemUpdate(spare_part_name="بلبر ج"),
        )
        assert updated.spare_part_name == "بلبر ج"

    def test_received_item_name_is_locked(self, db):
        fault = _fault(db)
        created = _request(db, fault, "SP/26/016", [
            SparePartRequestItemCreate(spare_part_name="كابل نحاسي", requested_quantity=4),
        ])
        services.update_item(
            db, _first_item(db, created["id"]),
            SparePartRequestItemUpdate(
                received_quantity=3, received_date=date(2026, 3, 7),
                recipient="أمين المخزن", supplier_institution="مؤسسة الواردات",
            ),
        )
        item = _first_item(db, created["id"])
        assert item.received_quantity == 3
        with pytest.raises(ValueError):
            services.update_item(db, item, SparePartRequestItemUpdate(spare_part_name="اسم آخر"))

    def test_library_item_still_editable_by_id_only(self, db):
        """التوافق: عميل قديم يرسل المعرّف وحده، بلا اسم."""
        part = _part(db, "رديتر مشعّ", "SP-32")
        fault = _fault(db)
        created = _request(db, fault, "SP/26/017", [
            SparePartRequestItemCreate(spare_part_id=part.id, requested_quantity=2),
        ])
        updated = services.update_item(
            db, _first_item(db, created["id"]),
            SparePartRequestItemUpdate(requested_quantity=9),
        )
        assert updated.spare_part_id == part.id
        assert updated.requested_quantity == 9


class TestReceivedRegister:
    def test_free_name_shows_in_the_received_register(self, db):
        fault = _fault(db)
        created = _request(db, fault, "SP/26/020", [
            SparePartRequestItemCreate(spare_part_name="مانيفولد حركة", requested_quantity=3),
        ])
        services.update_item(
            db, _first_item(db, created["id"]),
            SparePartRequestItemUpdate(
                received_quantity=2, received_date=date(2026, 3, 8),
                recipient="أمين المخزن", supplier_institution="مؤسسة الواردات",
            ),
        )
        rows = services.received_register(db)
        assert len(rows) == 1
        assert rows[0]["request_number"] == "SP/26/020"
        assert rows[0]["part_name"] == "مانيفولد حركة"
        assert rows[0]["received_quantity"] == 2
        assert rows[0]["recipient"] == "أمين المخزن"

    def test_library_name_still_shown_for_bound_items(self, db):
        part = _part(db, "رديتر مشعّ", "SP-40")
        fault = _fault(db)
        created = _request(db, fault, "SP/26/021", [
            SparePartRequestItemCreate(spare_part_id=part.id, requested_quantity=1),
        ])
        services.update_item(
            db, _first_item(db, created["id"]),
            SparePartRequestItemUpdate(
                received_quantity=1, received_date=date(2026, 3, 9),
                recipient="أمين المخزن", supplier_institution="مؤسسة الواردات",
            ),
        )
        rows = services.received_register(db)
        assert len(rows) == 1
        assert rows[0]["part_name"] == "رديتر مشعّ"


# ------------------------------------------------------------ النموذج في المتصفح

def test_template_offers_free_text_with_optional_suggestions():
    from pathlib import Path

    template = (
        Path(__file__).resolve().parents[1]
        / "app" / "modules" / "spare_parts_requests" / "templates" / "requests.html"
    ).read_text(encoding="utf-8")

    # الحقول الثلاثة (بند جديد، إضافة بند لطلب قائم، تعديل بند) لم تعد قوائم منسدلة.
    assert '<select class="new-part"' not in template
    assert '<select class="add-part"' not in template
    assert '<select class="edit-part"' not in template

    # وحقل نصي مع اقتراحات اختيارية من المكتبة.
    assert template.count('list="partSuggestions"') == 3
    assert "partIdByName" in template
    assert "spare_part_name" in template

    # وحقول الاستلام والتاريخ والمستلم والمؤسسة والملاحظات باقية.
    for field in ("edit-received", "edit-received-date", "edit-recipient", "edit-supplier", "edit-notes"):
        assert field in template
