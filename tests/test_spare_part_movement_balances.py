"""أرصدة الغيار المستلم وحالته: استلام ← توزيع ← إرجاع ← الرصيد.

الحالة لا تُقرأ من حقل يدوي، بل تُشتقّ من الأرصدة نفسها، وترتيبها من الأدق
إلى الأعم. والحدود على الخادم: التوزيع والإرجاع الزائد يُرفضان في الخدمة لا
في JavaScript، ولذلك هذا الملف ينادي الخدمة مباشرةً — لو كان القيد في الصفحة
وحدها لكان الطلب المباشر يمرّ.

يغطّي كذلك التحديث لا الإنشاء فقط: استثناء رقم الوثيقة في حسابات الأرصدة هو
ما يمنع الوثيقة من حساب نفسها ضمن أرصدتها.
"""

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
import re

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import model_registry  # noqa: F401  (يسجّل كل النماذج قبل create_all)
from app.database.base import Base
from app.modules.spare_parts_movements import services as movements
from app.modules.spare_parts_movements.models import SparePartMovementItem
from app.modules.spare_parts_movements.schemas import (
    MovementDocumentCreate,
    MovementDocumentUpdate,
    MovementItemCreate,
)

RECEIVED = date(2026, 3, 1)


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    try:
        yield session
    finally:
        session.close()


def _setup_shared(db):
    """عتاد وعطل مشتركان لكل بنود هذا الملف: الطلب يحتاج مصدراً ومعدة."""
    from app.modules.equipment.models import Equipment
    from app.modules.equipment_types.models import EquipmentModel, EquipmentType
    from app.modules.faults_repairs.models import Fault

    _COUNTER["n"] += 1
    suffix = _COUNTER["n"]
    eq_type = EquipmentType(name=f"شاحنات-أرصدة-{suffix}", measurement_unit="km")
    db.add(eq_type)
    db.flush()
    model = EquipmentModel(name=f"طراز أرصدة-{suffix}", equipment_type_id=eq_type.id)
    db.add(model)
    db.flush()
    equipment = Equipment(
        asset_code=f"BAL-{suffix}",
        registration_number=f"333-BAL-{suffix}",
        equipment_type_id=eq_type.id,
        equipment_model_id=model.id,
        technical_condition="ready",
        operational_status="available",
    )
    db.add(equipment)
    db.flush()
    fault = Fault(
        equipment_id=equipment.id,
        reported_date=RECEIVED,
        fault_type="عطل",
        description="وصف",
        severity="low",
        status="open",
        exploitation_impact="limited",
    )
    db.add(fault)
    db.commit()
    return equipment.id, fault.id


_COUNTER = {"n": 0}


def _received_item(db, received, supplier="المؤسسة الممونة"):
    """بند غيار مستلم جاهز للتوزيع، مبنيّ بالنموذج مباشرةً.

    الاختبار يهتم بأرصدة التوزيع والإرجاع وحدها، وشاشة الاستلام ليست جزءاً من
    ذلك — فمنشئ الطلب يضع الكميات بناءً على قواعد أخرى لا نحتاجها هنا.
    """
    from app.modules.spare_parts_requests.models import (
        SparePartRequest,
        SparePartRequestItem,
    )

    equipment_id, fault_id = _setup_shared(db)
    request = SparePartRequest(
        request_number=f"SR-BAL-{_COUNTER['n']}",
        request_date=RECEIVED,
        received_date=RECEIVED,
        source_type="fault",
        fault_id=fault_id,
        equipment_id=equipment_id,
        status="approved",
    )
    db.add(request)
    db.flush()
    item = SparePartRequestItem(
        request_id=request.id,
        part_name="فلتر",
        requested_quantity=received,
        received_quantity=received,
        received_date=RECEIVED,
        recipient="المستلم",
        supplier_institution=supplier,
    )
    db.add(item)
    db.commit()
    return item


def _item_id(document):
    """أول سند توزيع في الوثيقة: به يُرجع الغيار لاحقاً."""
    return document.items[0].id


def _add_legacy_return(db, item, quantity, number=None):
    """إرجاع قديم: سطر حركة بلا سند توزيع، كما في البيانات القائمة.

    هذه السطور موجودة فعلاً في القاعدة من قبل ربط الإرجاع بسند التوزيع،
    ولا تُنشئها الخدمة اليوم — فلا طريق إليها غير النموذج مباشرةً.
    """
    from app.modules.spare_parts_movements.models import SparePartMovementDocument

    _COUNTER["n"] += 1
    document = SparePartMovementDocument(
        document_number=number or f"R-LEGACY-{_COUNTER['n']}",
        document_type="return",
        document_date=RECEIVED + timedelta(days=2),
        issuer="المستلم",
        recipient=item.supplier_institution or "المؤسسة الممونة",
        beneficiary="المستلم",
    )
    db.add(document)
    db.flush()
    db.add(
        SparePartMovementItem(
            request_item_id=item.id, quantity=Decimal(str(quantity)), document_id=document.id
        )
    )
    db.commit()
    return document


def _lines(item_id, quantity, source_item_id=None, bypass_schema=False):
    """بنود الوثيقة، بمرّ على تحقق pydantic أو بتجاوزه.

    الكائن يبقى في الحالتين: ``model_construct`` يتخطّى التحقق ولا يغيّر
    النوع، والخدمة تقرأ البنود كسمات لا كمفاتيح.
    """
    line = {
        "request_item_id": item_id,
        "quantity": Decimal(str(quantity)),
        "source_item_id": source_item_id,
    }
    if bypass_schema:
        return [MovementItemCreate.model_construct(**line)]
    return [MovementItemCreate(**line)]


def _distribute(db, item, quantity, day=2, exclude=None, bypass_schema=False, received_item=None):
    """توزيع كمية من بند، إما بوثيقة جديدة أو بتعديل وثيقة قائمة.

    ``bypass_schema`` يبني الطلب بلا تحقق pydantic، ليمثّل حمولةٍ تصل إلى
    الخدمة دون أن تمرّ بالمخطط. ذاك هو السبب في أن يكون رفض الصفر والسالب
    في الخدمة فعلاً، لا تكراراً لقاعدة ``gt=0`` الموجودة في المخطط.
    """
    lines = _lines(item.id, quantity, bypass_schema=bypass_schema)
    if received_item is not None:
        lines[0].received_request_item_id = received_item.id
    if exclude:
        return movements.update_document(
            db,
            exclude,
            MovementDocumentUpdate.model_construct(
                document_number=None,
                document_date=RECEIVED + timedelta(days=day),
                recipient="الورشة",
                items=lines,
                source_document_id=None,
                notes=None,
            ),
        )
    _COUNTER["n"] += 1
    return movements.create_document(
        db,
        MovementDocumentCreate.model_construct(
            document_number=f"D-{_COUNTER['n']}",
            document_type="distribution",
            document_date=RECEIVED + timedelta(days=day),
            recipient="الورشة",
            items=lines,
        ),
    )


def _return(db, item, quantity, source_item_id, day=3, exclude=None, bypass_schema=False):
    """إرجاع من بند الاستلام؛ وسيط التوزيع محفوظ لتقليل تغيير الاستدعاءات."""
    return _return_received(
        db, item, quantity, day=day, exclude=exclude, bypass_schema=bypass_schema
    )


def _return_received(db, item, quantity, day=3, exclude=None, bypass_schema=False):
    """إرجاع مباشر من بند استلام، دون إنشاء وثيقة توزيع."""
    line_data = {
        "request_item_id": item.id,
        "received_request_item_id": item.id,
        "quantity": Decimal(str(quantity)),
    }
    line = (
        MovementItemCreate.model_construct(**line_data, source_item_id=None)
        if bypass_schema
        else MovementItemCreate(**line_data)
    )
    if exclude:
        return movements.update_document(
            db,
            exclude,
            MovementDocumentUpdate(
                document_date=RECEIVED + timedelta(days=day),
                items=[line],
            ),
        )
    _COUNTER["n"] += 1
    return movements.create_document(
        db,
        MovementDocumentCreate(
            document_number=f"R-DIRECT-{_COUNTER['n']}",
            document_type="return",
            document_date=RECEIVED + timedelta(days=day),
            items=[line],
        ),
    )


def _balances(db, item, exclude=None):
    db.expire_all()
    return movements._compute_balances(db, item, exclude)


# ------------------------------------------------------------- الحالات الخمس


def test_received_and_not_yet_distributed(db):
    item = _received_item(db, 10)
    balances = _balances(db, item)
    assert balances["distributed"] == 0
    assert balances["returned"] == 0
    assert balances["status"] == "received_not_distributed"
    assert balances["available_for_distribution"] == 10
    assert balances["remaining"] == 10


def test_partially_distributed(db):
    item = _received_item(db, 10)
    _distribute(db, item, 3)
    balances = _balances(db, item)
    assert balances["distributed"] == 3
    assert balances["status"] == "partially_distributed"
    assert balances["available_for_distribution"] == 7
    assert balances["remaining"] == 7


def test_fully_distributed(db):
    item = _received_item(db, 10)
    _distribute(db, item, 4)
    _distribute(db, item, 6, day=3)
    balances = _balances(db, item)
    assert balances["distributed"] == 10
    assert balances["returned"] == 0
    assert balances["status"] == "fully_distributed"
    assert balances["available_for_distribution"] == 0
    assert balances["remaining"] == 0


def test_distributed_then_fully_returned(db):
    item = _received_item(db, 10)
    _return_received(db, item, 10)
    balances = _balances(db, item)
    assert balances["distributed"] == 0
    assert balances["returned"] == 10
    assert balances["remaining"] == 0
    assert movements.return_register(db) == []


def test_part_remaining_with_the_entity(db):
    item = _received_item(db, 10)
    _return_received(db, item, 4)
    balances = _balances(db, item)
    assert balances["returned"] == 4
    assert movements.return_register(db)[0]["remaining_quantity"] == 6


def test_the_most_specific_state_wins_when_two_overlap(db):
    """استُلم 10 ووُزّع 3 ورُجع منها 1: تنطبق حالتان، فتظهر الأدق.

    «موزع جزئيًا» تنطبق (0 < 3 < 10)، و«جزء متبقٍ لدى الجهة» تنطبق أيضاً
    (0 < 1 < 3). الثانية أدق لأنها تذكر الإرجاع الذي لا تذكره الأولى.
    """
    item = _received_item(db, 10)
    _distribute(db, item, 3)
    _return_received(db, item, 1)
    balances = _balances(db, item)
    assert balances["distributed"] == 2
    assert balances["distributed_total"] == 3
    assert balances["returned"] == 1
    assert balances["remaining"] == 7
    assert movements.return_register(db)[0]["remaining_quantity"] == 6


# ------------------------------------------------------ منع تجاوز الكميات


def test_a_direct_return_can_settle_a_historical_over_distribution(db):
    """التوزيع التاريخي الزائد تُسوّيه إرجاعات الاستلام المباشرة."""
    item = _received_item(db, 3)
    _COUNTER["n"] += 1
    from app.modules.spare_parts_movements.models import SparePartMovementDocument

    distribution = SparePartMovementDocument(
        document_number=f"D-SETTLE-{_COUNTER['n']}",
        document_type="distribution",
        document_date=RECEIVED + timedelta(days=2),
        issuer="المخزن",
        recipient="الورشة",
    )
    db.add(distribution)
    db.flush()
    db.add(SparePartMovementItem(
        document_id=distribution.id,
        request_item_id=item.id,
        received_request_item_id=item.id,
        quantity=Decimal("4"),
    ))
    return_document = SparePartMovementDocument(
        document_number=f"R-SETTLE-{_COUNTER['n']}",
        document_type="return",
        document_date=RECEIVED + timedelta(days=3),
        issuer="المخزن",
        recipient=item.supplier_institution,
        beneficiary=item.supplier_institution,
    )
    db.add(return_document)
    db.flush()
    db.add(SparePartMovementItem(
        document_id=return_document.id,
        request_item_id=item.id,
        received_request_item_id=item.id,
        quantity=Decimal("1"),
    ))
    db.commit()

    balances = _balances(db, item)
    assert balances["distributed"] == 3
    assert balances["distributed_total"] == 4
    assert balances["returned"] == 1
    assert balances["available_for_distribution"] == 0
    assert balances["status"] == "fully_distributed"


def test_a_corrupt_historical_distribution_is_flagged_as_invalid(db):
    item = _received_item(db, 3)
    _COUNTER['n'] += 1
    from app.modules.spare_parts_movements.models import SparePartMovementDocument

    document = SparePartMovementDocument(
        document_number='D-CORRUPT-' + str(_COUNTER['n']),
        document_type='distribution',
        document_date=RECEIVED + timedelta(days=2),
        issuer='المخزن',
        recipient='الورشة',
    )
    db.add(document)
    db.flush()
    db.add(SparePartMovementItem(
        document_id=document.id, request_item_id=item.id,
        received_request_item_id=item.id, quantity=Decimal('4'),
    ))
    db.commit()

    balances = _balances(db, item)
    assert balances['received_quantity'] == 3
    assert balances['distributed'] == 4
    assert balances['available_for_distribution'] == 0
    assert balances['status'] == 'invalid_distribution_over_received'


def test_distribution_uses_the_explicit_received_item_as_its_balance_source(db):
    display_item = _received_item(db, 1)
    received_item = _received_item(db, 3)
    _distribute(db, display_item, 3, received_item=received_item)
    balances = _balances(db, received_item)
    assert balances['distributed'] == 3
    assert balances['available_for_distribution'] == 0
    assert balances['status'] == 'fully_distributed'

def test_a_distribution_beyond_what_was_received_is_refused(db):
    item = _received_item(db, 10)
    _distribute(db, item, 4)
    with pytest.raises(ValueError, match="المتاحة للتوزيع"):
        _distribute(db, item, 7, day=5)


def test_a_return_beyond_received_balance_after_distribution_is_refused(db):
    item = _received_item(db, 10)
    _distribute(db, item, 6)
    _return_received(db, item, 2)
    with pytest.raises(ValueError, match="القابلة للإرجاع"):
        _return_received(db, item, 3, day=6)


def test_distributing_exactly_the_remainder_is_allowed(db):
    item = _received_item(db, 10)
    _distribute(db, item, 4)
    _distribute(db, item, 6, day=3)
    assert _balances(db, item)["distributed"] == 10


def test_returnable_quantity_is_capped_by_the_received_source(db):
    """الإرجاع يستهلك الرصيد المستلم بعد طرح التوزيع، دون مصدر توزيع."""
    item = _received_item(db, 10)
    _distribute(db, item, 4)
    _return_received(db, item, 3)
    assert movements.return_register(db)[0]["remaining_quantity"] == 3

    with pytest.raises(ValueError, match="القابلة للإرجاع"):
        _return_received(db, item, 4, day=5)


def test_returnable_register_uses_the_received_source_ceiling(db):
    item = _received_item(db, 10)
    _return_received(db, item, 5)

    rows = movements.return_register(db)
    assert len(rows) == 1
    assert rows[0]["received_request_item_id"] == item.id
    assert rows[0]["returnable_quantity"] == 5


def test_received_item_can_be_returned_without_a_distribution(db):
    item = _received_item(db, 5)

    document = _return_received(db, item, 3)

    assert document.source_document_id is None
    assert document.items[0].source_item_id is None
    assert document.items[0].received_request_item_id == item.id
    assert _balances(db, item)["returned"] == 3
    assert movements.return_register(db)[0]["returnable_quantity"] == 2


def test_return_register_exposes_unallocated_received_items(db):
    """الغيار المستلم وغير الموزع يبقى قابلاً للإرجاع."""
    item = _received_item(db, 1)

    rows = movements.return_register(db)

    row = next(r for r in rows if r["request_item_id"] == item.id)
    assert row["received_quantity"] == 1
    assert row["distributed_quantity"] == 0
    assert row["returned_quantity"] == 0
    assert row["returnable_quantity"] == 1
    assert row["remaining_quantity"] == 1


def test_direct_return_cannot_exceed_the_remaining_received_quantity(db):
    item = _received_item(db, 5)
    _return_received(db, item, 4)

    with pytest.raises(ValueError, match="القابلة للإرجاع"):
        _return_received(db, item, 2, day=4)


def test_remaining_return_balance_subtracts_distribution_and_prior_returns(db):
    item = _received_item(db, 10)
    _distribute(db, item, 4)
    _return_received(db, item, 2)

    row = movements.return_register(db)[0]
    assert row["received_quantity"] == 10
    assert row["distributed_quantity"] == 4
    assert row["returned_quantity"] == 2
    assert row["remaining_quantity"] == 4


def test_updating_direct_return_excludes_its_existing_quantity(db):
    item = _received_item(db, 5)
    document = _return_received(db, item, 3)

    updated = _return_received(db, item, 5, day=4, exclude=document.id)

    assert updated.id == document.id
    assert updated.source_document_id is None
    assert updated.items[0].received_request_item_id == item.id
    assert _balances(db, item)["returned"] == 5


def test_unreceived_item_cannot_be_returned(db):
    item = _received_item(db, 5)
    item.received_quantity = 0
    db.commit()

    with pytest.raises(ValueError, match="لم يُستلم"):
        _return_received(db, item, 1)


def test_return_rejects_a_mismatched_received_source(db):
    item = _received_item(db, 10)
    other = _received_item(db, 5)
    line = MovementItemCreate.model_construct(
        request_item_id=item.id,
        received_request_item_id=other.id,
        quantity=Decimal("1"),
        source_item_id=None,
    )
    with pytest.raises(ValueError, match="بند الاستلام"):
        movements.create_document(
            db,
            MovementDocumentCreate.model_construct(
                document_number="R-MISMATCH",
                document_type="return",
                document_date=RECEIVED + timedelta(days=4),
                items=[line],
            ),
        )


def test_returning_exactly_the_remainder_is_allowed(db):
    item = _received_item(db, 10)
    _distribute(db, item, 6)
    _return_received(db, item, 2)
    _return_received(db, item, 2, day=6)
    balances = _balances(db, item)
    assert balances["returned"] == 4
    assert movements.return_register(db) == []


@pytest.mark.parametrize("quantity", [0, -1, -5])
def test_a_zero_or_negative_distribution_is_refused(db, quantity):
    """الصفر والسالب مرفوضان في الخدمة نفسها، لا في الصفحة وحدها.

    الطلب هنا يبني نفسه متجاوزاً مخطط pydantic، لأن المخطط يرفض الصفر
    أصلاً بقاعدته ``gt=0``. فلو اكتُفي بمرور الاختبار من المخطط لما عرفنا
    أن للخدمة قيداً خاصاً بها — ولما منع الطلب المباشر الذي يتجاوز المخطط.
    """
    item = _received_item(db, 10)
    with pytest.raises(ValueError, match="أكبر من صفر"):
        _distribute(db, item, quantity, bypass_schema=True)


@pytest.mark.parametrize("quantity", [0, -3])
def test_a_zero_or_negative_return_is_refused(db, quantity):
    item = _received_item(db, 10)
    with pytest.raises(ValueError, match="أكبر من صفر"):
        _return_received(db, item, quantity, bypass_schema=True)


@pytest.mark.parametrize("quantity", [0, -2, "2.5"])
def test_a_bad_quantity_is_refused_on_update_too(db, quantity):
    """التعديل مسار ثانٍ يدخل نفس الخدمة، فيجب أن يحمل القيد نفسه."""
    item = _received_item(db, 10)
    doc = _distribute(db, item, 4)
    with pytest.raises(ValueError):
        _distribute(db, item, quantity, day=5, exclude=doc.id, bypass_schema=True)


def test_a_fractional_quantity_is_refused(db):
    """كميات الغيار أعداد صحيحة؛ الكسر ليس كمية قطعة."""
    item = _received_item(db, 10)
    with pytest.raises(ValueError, match="عدداً صحيحاً"):
        _distribute(db, item, Decimal("2.5"), bypass_schema=True)


def test_the_schema_also_refuses_a_bad_quantity(db):
    """المخطط يرفضه أيضاً — القيد في عمقين لا في عمق واحد.

    الاختبار يسجّل أن ``gt=0`` في ``MovementItemCreate`` ما زال قائماً،
    فحذفه لاحقاً يكسر هذا الاختبار قبل أن يصل الطلب إلى الخدمة.
    """
    item = _received_item(db, 10)
    with pytest.raises(ValidationError):
        _distribute(db, item, 0)


# ------------------------------------------------------------------ التحديث


def test_updating_a_distribution_does_not_count_the_old_line(db):
    """التحديث يحسب الوثيقة نفسها مرتين لو لم يُستثنَ رقمها.

    بدون الاستثناء كان أي تعديل — حتى تعديل لا يغيّر الكمية — يُرفض، لأن
    الوثيقة كانت تحسب نفسها ضمن أرصدتها فتجمع الكمية القديمة والجديدة.
    """
    item = _received_item(db, 10)
    doc = _distribute(db, item, 4)

    _distribute(db, item, 7, day=5, exclude=doc.id)

    balances = _balances(db, item)
    assert balances["distributed"] == 7
    assert balances["available_for_distribution"] == 3
    assert balances["status"] == "partially_distributed"


def test_updating_a_distribution_still_cannot_exceed_the_received(db):
    """الاستثناء يريح التعديل، ولا يفتح باب التجاوز."""
    item = _received_item(db, 10)
    doc = _distribute(db, item, 4)
    _distribute(db, item, 3, day=5)

    with pytest.raises(ValueError, match="المتاحة للتوزيع"):
        _distribute(db, item, 8, day=6, exclude=doc.id)


def test_updating_a_return_does_not_count_the_old_line(db):
    item = _received_item(db, 10)
    _distribute(db, item, 4)
    ret = _return_received(db, item, 3)

    _return_received(db, item, 6, day=6, exclude=ret.id)

    balances = _balances(db, item)
    assert balances["returned"] == 6
    assert movements.return_register(db) == []


def test_updating_a_return_still_cannot_exceed_received_balance(db):
    item = _received_item(db, 10)
    _distribute(db, item, 4)
    ret = _return_received(db, item, 1)

    with pytest.raises(ValueError, match="القابلة للإرجاع"):
        _return_received(db, item, 7, day=6, exclude=ret.id)


def test_the_balances_can_look_past_the_document_being_edited(db):
    """الأرصدة تُقرأ باستثناء رقم الوثيقة، فلا تحسب الوثيقة نفسها.

    لولا الاستثناء لظهرت الكمية الموزعة في وثيقة التعديل مرتين: مرة من
    معناها الصحيح ومرة من حساب الوثيقة لنفسها.
    """
    item = _received_item(db, 10)
    _distribute(db, item, 4)
    return_doc = _return_received(db, item, 1)

    whole = _balances(db, item)
    assert whole["distributed"] == 3
    assert whole["distributed_total"] == 4
    assert whole["returned"] == 1
    assert whole["available_for_distribution"] == 5
    assert whole["remaining"] == 6

    without = _balances(db, item, exclude=return_doc.id)
    assert without["distributed"] == 4
    assert without["returned"] == 0
    assert without["available_for_distribution"] == 6
    assert without["remaining"] == 6


def test_the_history_page_reports_the_same_balances(db):
    from app.modules.spare_parts_requests import services as requests_services

    item = _received_item(db, 10)
    doc = _distribute(db, item, 6)
    _return(db, item, 2, _item_id(doc))

    balances = movements.history(db, item.id)["balances"]
    assert balances["distributed"] == 4
    assert balances["distributed_total"] == 6
    assert balances["returned"] == 2
    assert balances["available_for_distribution"] == 2
    assert balances["remaining"] == 4
    assert balances["status"] == "partially_remaining_with_entity"


def test_a_legacy_return_without_a_distribution_goes_back_to_stock(db):
    """إرجاع قديم بلا سند توزيع يُخرج القطعة من المتاح من جديد.

    ولولا طرحه من المتاح لبقيت القطعة محجوزة إلى الأبد.
    """
    item = _received_item(db, 10)
    _distribute(db, item, 6)
    _add_legacy_return(db, item, 2)

    balances = _balances(db, item)
    assert balances["legacy_returned"] == 2
    assert balances["returned"] == 2
    assert balances["distributed"] == 4
    assert balances["distributed_total"] == 6
    # المتاح 10 - 6 - 2: القطعةان العائدتان صارتا متاحتين للتوزيع
    assert balances["available_for_distribution"] == 2
    # والمتبقي لدى الجهة لا يمسّه الإرجاع القديم: هو لم يردْ من الجهة
    assert balances["remaining_with_entity"] == 6


def test_editing_a_document_restores_the_full_available_quantity(db):
    """عند تعديل وثيقة، يُستثنى رقمها من الرصيد فيعود المتاح كاملاً.

    السطر يبقى معروضاً — ذاك هو المقصود: السطر المراد تعديله لا بدّ أن يظهر
    بكميته الكاملة حتى يُعاد إدخال كميته، لا أن يختفي ولا أن يعرض ناقصاً.
    """
    item = _received_item(db, 10)
    doc = _distribute(db, item, 4)

    def row(exclude=None):
        return next(
            r for r in movements.available_register(db, exclude_document_id=exclude)
            if r["request_item_id"] == item.id
        )

    assert row()["available_quantity"] == 6, "المتاح بعد التوزيع 10 - 4"
    assert row(doc.id)["available_quantity"] == 10, (
        "استثناء وثيقة التعديل لم يُرِد الكمية الموزوعة إلى الرصيد"
    )


# ------------------------------------------------------ صفحة الغيار المستلم


BALANCE_KEYS = (
    "received_quantity",
    "distributed",
    "remaining",
    "returned",
)


def _register_row(db, received):
    from app.modules.spare_parts_requests import services as requests_services

    return next(
        r for r in requests_services.received_register(db)
        if r["received_quantity"] == received
    )


def test_the_received_register_shows_the_balances_and_the_state(db):
    item = _received_item(db, 10)
    doc = _distribute(db, item, 6)
    _return(db, item, 2, _item_id(doc))

    row = _register_row(db, 10)
    assert {k: row[k] for k in BALANCE_KEYS} == {
        "received_quantity": 10,
        "distributed": 4,
        "remaining": 4,
        "returned": 2,
    }


def test_balance_has_only_received_distributed_remaining_and_returned(db):
    item = _received_item(db, 10)
    doc = _distribute(db, item, 6)
    _return(db, item, 2, _item_id(doc))

    balances = _balances(db, item)

    assert balances["received_quantity"] == 10
    assert balances["distributed"] == 4
    assert balances["remaining"] == 4
    assert balances["returned"] == 2
    assert balances["received_quantity"] == (
        balances["distributed"] + balances["remaining"] + balances["returned"]
    )


def test_deleting_a_return_cannot_create_over_distribution_history(db):
    item = _received_item(db, 3)

    _COUNTER["n"] += 1
    from app.modules.spare_parts_movements.models import SparePartMovementDocument

    distribution = SparePartMovementDocument(
        document_number=f"D-OVER-{_COUNTER['n']}",
        document_type="distribution",
        document_date=RECEIVED + timedelta(days=2),
        issuer="المخزن",
        recipient="الورشة",
    )
    db.add(distribution)
    db.flush()
    db.add(
        SparePartMovementItem(
            document_id=distribution.id,
            request_item_id=item.id,
            received_request_item_id=item.id,
            quantity=Decimal("4"),
        )
    )

    return_document = SparePartMovementDocument(
        document_number=f"R-OVER-{_COUNTER['n']}",
        document_type="return",
        document_date=RECEIVED + timedelta(days=3),
        issuer="المخزن",
        recipient=item.supplier_institution,
        beneficiary=item.supplier_institution,
    )
    db.add(return_document)
    db.flush()
    db.add(
        SparePartMovementItem(
            document_id=return_document.id,
            request_item_id=item.id,
            received_request_item_id=item.id,
            quantity=Decimal("1"),
        )
    )
    db.commit()

    balances = _balances(db, item)
    # التوزيع التاريخي 4 صار 3 موزعة فعليًا بعد إرجاع 1، لذلك الرصيد
    # الحالي مكتمل. لكن حذف الإرجاع سيعيد حالة التجاوز، ولذلك يُمنع الحذف.
    assert balances["status"] == "fully_distributed"
    assert balances["distributed"] == 3
    assert balances["distributed_total"] == 4
    assert balances["returned"] == 1

    with pytest.raises(ValueError, match="حذف الإرجاع"):
        movements.delete_document(db, return_document.id)

    assert _balances(db, item)["returned"] == 1


def test_deleting_direct_return_restores_received_return_balance(db):
    item = _received_item(db, 10)
    _distribute(db, item, 4)
    document = _return_received(db, item, 2)

    assert movements.return_register(db)[0]["remaining_quantity"] == 4
    movements.delete_document(db, document.id)

    row = movements.return_register(db)[0]
    assert row["returned_quantity"] == 0
    assert row["remaining_quantity"] == 6


def test_the_received_register_agrees_with_the_distribution_page(db):
    """رقمان للبند نفسه لا يصح أن يخرجا من حسابين مختلفين."""
    item = _received_item(db, 10)
    _distribute(db, item, 6)
    legacy = _add_legacy_return(db, item, 2)

    row = _register_row(db, 10)
    page = next(
        r for r in movements.available_register(db)
        if r["request_item_id"] == item.id
    )
    # سجل الاستلام يعرض الرصيد المرئي الجديد، بينما صفحة التوزيع تحتفظ
    # برصيد التشغيل الداخلي اللازم لمنع تجاوز الكمية المستلمة.
    assert row["received_quantity"] == 10
    assert row["distributed"] == 4
    assert row["remaining"] == 4
    assert row["returned"] == 2
    assert page["available_quantity"] == 2
    assert legacy


def test_the_received_register_keeps_the_existing_columns(db):
    """الأعمدة التي كانت في السجل قبل الأرصدة ما زالت موجودة."""
    item = _received_item(db, 10)
    row = _register_row(db, 10)
    for key in (
        "request_number",
        "part_name",
        "requested_quantity",
        "received_date",
        "equipment",
        "registration_number",
        "recipient",
        "supplier_institution",
    ):
        assert key in row, f"عمود {key} اختفى من سجل الغيار المستلم"
    assert row["equipment"]["asset_code"].startswith("BAL-")


# --------------------------------------------------------- عرض الصفحة نفسها

TEMPLATE = (
    Path(__file__).resolve().parents[1]
    / "app" / "modules" / "spare_parts_requests" / "templates" / "received.html"
)

# الأعمدة المرئية في سجل الاستلام: أربعة عناصر للرصد المالي فقط،
# مع أعمدة التعريف والحركة والتاريخ والجهة.
COLUMNS = {
    "request_number": "رقم الطلب",
    "part_name": "الغيار",
    "asset_code": "العتاد",
    "received_quantity": "المستلم",
    "distributed": "الموزع",
    "remaining": "الباقي",
    "returned": "المرتجع",
    "last_movement_type": "آخر الحركة",
    "received_date": "تاريخ الاستلام",
    "registration_number": "رقم التسجيل",
    "recipient": "المستلم إليه",
    "supplier_institution": "المؤسسة الممونة",
}


def _page():
    return TEMPLATE.read_text(encoding="utf-8")


def test_every_balance_column_is_shown_under_its_own_header():
    """رأس السجل وترتيب خلاياه يطابقان الأرصدة المرئية المطلوبة."""
    html = _page()
    headers = re.findall(r"<th>(.*?)</th>", html)
    assert headers == list(COLUMNS.values())

    builder = html[html.index("function render()") : html.index("function esc(")]
    expected_fragments = [
        "x.request_number",
        "x.part_name",
        "x.equipment?.asset_code",
        "x.received_quantity",
        "x.distributed",
        "x.remaining",
        "x.returned",
        "MOVEMENT_LABELS[x.last_movement_type]",
        "x.received_date",
        "x.registration_number",
        "x.recipient",
        "x.supplier_institution",
    ]
    positions = [builder.index(fragment) for fragment in expected_fragments]
    assert positions == sorted(positions)


def test_the_row_spans_the_same_number_of_columns_as_the_header():
    html = _page()
    columns = len(re.findall(r"<th>", html))
    assert columns == len(COLUMNS)
    for colspan in re.findall(r'colspan="(\d+)"', html):
        assert int(colspan) == columns, (
            f"صف رسالة بعرض {colspan} وعمود واحد، والرأس {columns}"
        )


def test_the_received_page_renders_only_the_four_balance_parts():
    html = _page()
    assert "x.received_quantity" in html
    assert "x.distributed" in html
    assert "x.remaining" in html
    assert "x.returned" in html
    assert "available_for_distribution" not in html
    assert "STATUS_LABELS" not in html
    assert "x.status" not in html


def test_the_received_register_exact_example_is_three_one_one_one(db):
    """الحالة الفعلية المطلوبة: 3 مستلمة، توزيعا 1+1، وإرجاع 1.

    الرصيد المرئي يجب أن يبقى أربعة أجزاء متسقة:
    3 = 1 موزعة فعلياً + 1 باقٍ + 1 مرتجع.
    """
    item = _received_item(db, 3)
    first = _distribute(db, item, 1, day=2)
    _distribute(db, item, 1, day=3)
    _return(db, item, 1, day=4)

    row = _register_row(db, 3)
    assert row["received_quantity"] == 3
    assert row["distributed"] == 1
    assert row["remaining"] == 1
    assert row["returned"] == 1
    assert row["received_quantity"] == (
        row["distributed"] + row["remaining"] + row["returned"]
    )
    assert first.items[0].quantity == Decimal("1")


def test_the_page_has_no_lifecycle_states_of_its_own():
    """لا تُضاف حالات من خارج منطق الأرصدة، حتى لو كان لها عنوان عربي."""
    html = _page()
    for unwanted in ("قيد الفحص", "مقبول", "مرفوض", "مرجع للمورد", "ملغى"):
        assert unwanted not in html
