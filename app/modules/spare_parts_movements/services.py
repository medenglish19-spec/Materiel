from decimal import Decimal

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased, joinedload

from app.modules.faults_repairs.models import Repair
from app.modules.spare_parts_requests.models import SparePartRequest, SparePartRequestItem
from .models import SparePartMovementDocument, SparePartMovementItem
from .schemas import MovementDocumentCreate, MovementDocumentUpdate

DOCUMENT_NUMBER_TAKEN = "رقم الوثيقة مستخدم مسبقًا، يرجى إدخال رقم آخر."
WAREHOUSE_LABEL = "المخزن"


def _sum(values):
    return sum((Decimal(str(v or 0)) for v in values), Decimal("0"))


def _at_least_zero(value):
    return value if value > 0 else Decimal("0")


def _quantity(value, what="الكمية"):
    """يرفض ما لا يمكن أن تكون عليه كمية غيار، على الخادم لا في الصفحة.

    القواعد الثلاث معاً: الصفر والسالب لا معنى لهما لحركة غيار، وقاعدة المشروع
    أن كميات الغيار أعداد صحيحة فلا كسر. الواجهة ترشّح هذه القطع في
    JavaScript، لكن ذلك الرشّح يمكن تجاوزه بإرسال الطلب مباشرة؛ القيد هنا هو
    الذي يملكه الخادم فعلاً.

    يُفحص الكسر قبل المقارنة لأن 2.5 ليس عدداً صحيحاً أصلاً، ورفضه كسالب
    سيقود إلى رسالة مضلّلة.
    """
    quantity = Decimal(str(value if value is not None else 0))
    if quantity != quantity.to_integral_value():
        raise ValueError(f"{what} يجب أن تكون عدداً صحيحاً")
    if quantity <= 0:
        raise ValueError(f"{what} يجب أن تكون أكبر من صفر")
    return quantity


def _receipt_date(item):
    return item.request.received_date or item.received_date


def _number(value):
    value = (value or "").strip()
    if not value:
        raise ValueError("رقم الوثيقة مطلوب")
    return value


def _unique_number(db, number, exclude=None):
    q = db.query(SparePartMovementDocument.id).filter(
        SparePartMovementDocument.document_number == number
    )
    if exclude:
        q = q.filter(SparePartMovementDocument.id != exclude)
    if q.first():
        raise ValueError(DOCUMENT_NUMBER_TAKEN)


def _distribution_total(db, received_request_item_id, exclude=None):
    """إجمالي التوزيع المنسوب إلى بند الاستلام الحقيقي، مع توافق السجلات القديمة."""
    q = db.query(SparePartMovementItem.quantity).join(SparePartMovementDocument).filter(
        SparePartMovementDocument.document_type == "distribution",
        or_(
            SparePartMovementItem.received_request_item_id == received_request_item_id,
            (
                SparePartMovementItem.received_request_item_id.is_(None)
                & (SparePartMovementItem.request_item_id == received_request_item_id)
            ),
        ),
    )
    if exclude:
        q = q.filter(SparePartMovementDocument.id != exclude)
    return _sum([x[0] for x in q.all()])


def _legacy_return_total(db, request_item_id, exclude=None):
    q = db.query(SparePartMovementItem.quantity).join(SparePartMovementDocument).filter(
        SparePartMovementDocument.document_type == "return",
        SparePartMovementItem.source_item_id.is_(None),
        or_(
            SparePartMovementItem.received_request_item_id == request_item_id,
            (
                SparePartMovementItem.received_request_item_id.is_(None)
                & (SparePartMovementItem.request_item_id == request_item_id)
            ),
        ),
    )
    if exclude:
        q = q.filter(SparePartMovementDocument.id != exclude)
    return _sum([x[0] for x in q.all()])


def _distribution_totals(db, request_item_ids, exclude=None):
    """نفس `_distribution_total` لكل البنود دفعةً واحدة، مُجمَّعة بالمعرّف."""
    if not request_item_ids:
        return {}
    q = (
        db.query(
            func.coalesce(
                SparePartMovementItem.received_request_item_id,
                SparePartMovementItem.request_item_id,
            ),
            func.sum(SparePartMovementItem.quantity),
        )
        .join(SparePartMovementDocument, SparePartMovementItem.document_id == SparePartMovementDocument.id)
        .filter(
            SparePartMovementDocument.document_type == "distribution",
            or_(
                SparePartMovementItem.received_request_item_id.in_(request_item_ids),
                (
                    SparePartMovementItem.received_request_item_id.is_(None)
                    & (SparePartMovementItem.request_item_id.in_(request_item_ids))
                ),
            ),
        )
    )
    if exclude:
        q = q.filter(SparePartMovementDocument.id != exclude)
    # الـ GROUP BY صريح ضروري: بلاه تُعيد SQLite صفاً واحداً فقط — مفتاحاً
    # عشوائياً ومجموع كل البنود — فيُنسب إجمالي القاعدة كلها إلى بند واحد
    # ويظهر بندٌ آخر بموزّع صفر، والسجل يقرأ 3/3/0/1 بدل 3/1/1/1.
    q = q.group_by(
        func.coalesce(
            SparePartMovementItem.received_request_item_id,
            SparePartMovementItem.request_item_id,
        )
    )
    return {row[0]: _sum([row[1]]) for row in q.all()}


def _legacy_return_totals(db, request_item_ids, exclude=None):
    """نفس `_legacy_return_total` لكل البنود دفعةً واحدة."""
    if not request_item_ids:
        return {}
    q = (
        db.query(
            func.coalesce(
                SparePartMovementItem.received_request_item_id,
                SparePartMovementItem.request_item_id,
            ),
            func.sum(SparePartMovementItem.quantity),
        )
        .join(SparePartMovementDocument, SparePartMovementItem.document_id == SparePartMovementDocument.id)
        .filter(
            SparePartMovementDocument.document_type == "return",
            SparePartMovementItem.source_item_id.is_(None),
            func.coalesce(
                SparePartMovementItem.received_request_item_id,
                SparePartMovementItem.request_item_id,
            ).in_(request_item_ids),
        )
    )
    if exclude:
        q = q.filter(SparePartMovementDocument.id != exclude)
    # GROUP BY صريح كما في `_distribution_totals`: بلاه يعود مجموع كل
    # الإرجاعات القديمة على بند واحد بدل أن يُوزّع على أصحابها.
    q = q.group_by(
        func.coalesce(
            SparePartMovementItem.received_request_item_id,
            SparePartMovementItem.request_item_id,
        )
    )
    return {row[0]: _sum([row[1]]) for row in q.all()}


def _returned_totals(db, request_item_ids, exclude=None):
    """إجمالي الكمية المرتجعة من توزيعات كل بند، مُجمَّعة بالمعرّف.

    الإرجاع لا يُقاس على البند مباشرةً بل على سند توزيعه: البند الإرجاعي
    و«سند التوزيع» المشار إليه جدول واحد، فالوصل بينهما يحتاج اسماً بديلاً
    حقيقياً. استيراد العمود باسم آخر لا يصنع اسماً بديلاً، فيصير SQL هكذا
    ``JOIN spare_part_movement_items ON ... = ...id`` ويقول SQLite عموداً
    ملتبساً لأن ``quantity`` موجود على الجانبين.
    """
    if not request_item_ids:
        return {}
    DistItem = aliased(SparePartMovementItem)
    DistDocument = aliased(SparePartMovementDocument)
    q = (
        db.query(
            func.coalesce(
                DistItem.received_request_item_id,
                DistItem.request_item_id,
            ),
            func.sum(SparePartMovementItem.quantity),
        )
        .select_from(SparePartMovementItem)
        .join(SparePartMovementDocument, SparePartMovementItem.document_id == SparePartMovementDocument.id)
        .join(DistItem, SparePartMovementItem.source_item_id == DistItem.id)
        .join(DistDocument, DistItem.document_id == DistDocument.id)
        .filter(
            SparePartMovementDocument.document_type == "return",
            DistDocument.document_type == "distribution",
            func.coalesce(
                DistItem.received_request_item_id,
                DistItem.request_item_id,
            ).in_(request_item_ids),
        )
    )
    if exclude:
        q = q.filter(SparePartMovementDocument.id != exclude)
    # GROUP BY صريح كما في `_distribution_totals`: بلاه يعود مجموع
    # الإرجاعات على بندٍ واحد عشوائي بدل إرجاعات كل بند.
    q = q.group_by(
        func.coalesce(
            DistItem.received_request_item_id,
            DistItem.request_item_id,
        )
    )
    return {row[0]: _sum([row[1]]) for row in q.all()}


def _balances_maps(db, request_item_ids, exclude=None):
    """المجاميع الثلاثة لكل البنود في ثلاثة استعلامات، لا ثلاثة لكل بند."""
    ids = list(dict.fromkeys(request_item_ids))
    return {
        "distributed": _distribution_totals(db, ids, exclude),
        "returned_from_distributed": _returned_totals(db, ids, exclude),
        "legacy_returned": _legacy_return_totals(db, ids, exclude),
    }


def _available(received_qty, distributed, returned_from_distributed, receipt_returned):
    """المتاح = المستلم − الموزع الصافي − ما أُعيد إلى المورّد."""
    distributed_after_returns = distributed - returned_from_distributed
    if (
        received_qty < 0
        or distributed < 0
        or returned_from_distributed < 0
        or receipt_returned < 0
        or returned_from_distributed > distributed
        or distributed_after_returns + receipt_returned > received_qty
    ):
        return Decimal("0")
    return _at_least_zero(received_qty - distributed_after_returns - receipt_returned)


def available_quantity(db, item, exclude=None):
    return _available(
        Decimal(str(item.received_quantity or 0)),
        _distribution_total(db, item.id, exclude),
        _returned_total_by_received_item(db, item.id, exclude),
        _legacy_return_total(db, item.id, exclude),
    )


def _return_total(db, source_item_id, exclude=None):
    q = db.query(SparePartMovementItem.quantity).join(SparePartMovementDocument).filter(
        SparePartMovementDocument.document_type == "return",
        SparePartMovementItem.source_item_id == source_item_id,
    )
    if exclude:
        q = q.filter(SparePartMovementDocument.id != exclude)
    return _sum([x[0] for x in q.all()])


def _returned_total_by_received_item(db, received_request_item_id, exclude=None):
    return _returned_totals(db, [received_request_item_id], exclude).get(
        received_request_item_id, Decimal("0")
    )


def _returned_total_by_distribution_item(db, distribution_item_id, exclude=None):
    q = db.query(SparePartMovementItem.quantity).join(SparePartMovementDocument).filter(
        SparePartMovementDocument.document_type == "return",
        SparePartMovementItem.source_item_id == distribution_item_id,
    )
    if exclude:
        q = q.filter(SparePartMovementDocument.id != exclude)
    return _sum([x[0] for x in q.all()])


def returnable_quantity(db, distribution_item, exclude=None):
    """الكمية القابلة للإرجاع = أصغر رصيد بين الاستلام والتوزيع.

    received_request_item_id يحدد مصدر الاستلام الحقيقي، بينما source_item_id
    يحدد بند التوزيع الذي خرجت منه الكمية. السجلات القديمة التي لا تحمل
    received_request_item_id تستعمل request_item_id كمسار توافق.
    """
    if not distribution_item:
        return Decimal("0")
    received_item_id = getattr(distribution_item, "received_request_item_id", None) or distribution_item.request_item_id
    received_item = db.query(SparePartRequestItem).filter(
        SparePartRequestItem.id == received_item_id
    ).first()
    if received_item is None:
        return Decimal("0")

    returned_from_distributed = _returned_total_by_received_item(db, received_item_id, exclude)
    receipt_returned = _legacy_return_total(db, received_item_id, exclude)
    remaining_received = Decimal(str(received_item.received_quantity or 0)) - receipt_returned
    remaining_distributed = _distribution_total(db, received_item_id, exclude) - returned_from_distributed
    return _at_least_zero(min(remaining_received, remaining_distributed))


def _status(received, distributed, returned_from_distributed, receipt_returned):
    """الحالة مشتقّة من الأرصدة نفسها، لا من حقل حالة يدوي.

    الترتيب هنا هو الترتيب الأكثر تحديداً أولاً: متى تداخلت حالتان انطبقت
    الأدق. مثال: بند استُلم 10 ووُزّع 3 رُجع منها 1، فينطبق «موزع جزئيًا»
    (0 < 3 < 10) و«جزء متبقٍ لدى الجهة» (0 < 1 < 3) معاً؛ والثانية أدق لأنها
    تذكر الإرجاع الذي لا تذكره الأولى.

      1. مرتجع بالكامل  → رُدّ كل ما وُزّع
      2. جزء متبقٍ       → إرجاع جزئي: 0 < رُجع < وُزّع
      3. موزع بالكامل   → وُزّع كل ما استُلم ولا إرجاع
      4. موزع جزئيًا     → 0 < وُزّع < استُلم
      5. لم يوزع         → لم يُوزّع شيء
    """
    if (
        received < 0
        or distributed < 0
        or returned_from_distributed < 0
        or receipt_returned < 0
        or returned_from_distributed > distributed
    ):
        return "invalid_movement_balance"
    net_distributed = distributed - returned_from_distributed
    if net_distributed + receipt_returned > received:
        return "invalid_distribution_over_received"
    if distributed > 0 and returned_from_distributed == distributed:
        return "distributed_then_fully_returned"
    if received <= 0 or net_distributed <= 0:
        return "received_not_distributed"
    if net_distributed == received and receipt_returned == 0:
        return "fully_distributed"
    if returned_from_distributed > 0:
        return "partially_remaining_with_entity"
    return "partially_distributed"


def _at_least_zero(value):
    return value if value > 0 else Decimal("0")


def _balance_from_maps(item, maps):
    """رصيد بند واحد من المجاميع المحسوبة لكل البنود.

    الحساب كله هنا، لا في المجمّع ولا في دالة البند الواحد: فالمساران
    (بند ببند، أو دفعة واحدة) يقرآن هذه الدالة، فلا يمكن أن يختلفا.
    """
    distributed = maps["distributed"].get(item.id, Decimal("0"))
    # إرجاع مرتبط ببند توزيع يخص هذا البند تحديداً
    returned_from_distributed = maps["returned_from_distributed"].get(item.id, Decimal("0"))
    # إرجاع قديم مسجَّل على البند نفسه بلا سند توزيع
    legacy_returned = maps["legacy_returned"].get(item.id, Decimal("0"))

    received_qty = Decimal(str(item.received_quantity or 0))
    # لا يُنقص الإرجاع المباشر الذي يعكس الاستلام إجمالي التوزيع.
    distributed_actual = distributed - returned_from_distributed
    remaining = received_qty - distributed_actual - legacy_returned
    status = _status(
        received_qty,
        distributed,
        returned_from_distributed,
        legacy_returned,
    )
    return {
        "received_quantity": received_qty,
        "distributed": distributed_actual,
        "distributed_total": distributed,
        "returned": legacy_returned,
        "remaining": remaining,
        "remaining_with_entity": distributed_actual,
        "returned_from_distributed": returned_from_distributed,
        "legacy_returned": legacy_returned,
        "available_for_distribution": (
            _available(received_qty, distributed, returned_from_distributed, legacy_returned)
            if not status.startswith("invalid_")
            else Decimal("0")
        ),
        "status": status,
    }


def _balances_for(db, items, exclude=None):
    """أرصدة عدة بنود بثلاثة استعلامات مهما كثرت البنود.

    حساب كل بند على حدة يكلّف ثلاثة استعلامات لكل صف، فتصير تكلفة السجل
    ثلاثة أضعاف عدد البنود: صفحة واحدة تفتح مئات الاستعلامات على قاعدة
    فيها بنود كثيرة.
    """
    items = list(items)
    maps = _balances_maps(db, [item.id for item in items], exclude)
    return {item.id: _balance_from_maps(item, maps) for item in items}


def _compute_balances(db, item, exclude=None):
    """أرصدة بند غيار مستلم: استلام ← توزيع ← إرجاع ← الرصيد الحالي.

    ``exclude`` هو رقم الوثيقة قيد التعديل، فتُستثنى بنودها من الحساب. لولا
    ذلك لحُسب السطر القديم مرتين عند التعديل، فيُرفض كل تعديل — حتى تعديل
    لا يغيّر الكمية — لأن الوثيقة تحسب نفسها ضمن نفسها.
    """
    return _balances_for(db, [item], exclude)[item.id]


def _item(db, item_id):
    return db.query(SparePartRequestItem).options(
        joinedload(SparePartRequestItem.request).joinedload(SparePartRequest.equipment),
        joinedload(SparePartRequestItem.spare_part),
    ).filter(SparePartRequestItem.id == item_id).with_for_update().first()


def _distribution_line(db, item_id, quantity, document_date, exclude=None, received_request_item_id=None):
    quantity = _quantity(quantity)
    item = _item(db, item_id)
    if not item:
        raise ValueError("بند الغيار غير موجود")
    received_id = received_request_item_id or item_id
    received_item = _item(db, received_id)
    if not received_item:
        raise ValueError("بند الاستلام غير موجود")
    if received_item.received_quantity <= 0:
        raise ValueError("لا يمكن توزيع غيار لم يُستلم")
    receipt = _receipt_date(received_item)
    if not receipt:
        raise ValueError("لا يمكن التوزيع قبل تسجيل تاريخ الاستلام")
    if document_date < receipt:
        raise ValueError("تاريخ التوزيع لا يمكن أن يكون قبل تاريخ الاستلام")
    available = available_quantity(db, received_item, exclude)
    if quantity > available:
        raise ValueError(f"الكمية المتاحة للتوزيع هي {available} فقط")
    return item, received_id


def _return_line(db, source_item_id, request_item_id, quantity, document_date, exclude=None):
    quantity = _quantity(quantity)
    source = db.query(SparePartMovementItem).options(
        joinedload(SparePartMovementItem.document),
        joinedload(SparePartMovementItem.request_item).joinedload(SparePartRequestItem.request),
        joinedload(SparePartMovementItem.received_request_item),
    ).filter(SparePartMovementItem.id == source_item_id).with_for_update().first()
    if not source or source.document.document_type != "distribution":
        raise ValueError("الإرجاع يجب أن يرتبط ببند توزيع صحيح")
    item = source.request_item
    received_item = source.received_request_item or item
    if source.request_item_id != request_item_id:
        raise ValueError("مصدر الاستلام لا يطابق بند التوزيع")
    receipt = _receipt_date(received_item)
    if not receipt:
        raise ValueError("لا يمكن الإرجاع قبل تسجيل تاريخ الاستلام")
    if document_date < receipt:
        raise ValueError("تاريخ الإرجاع لا يمكن أن يكون قبل تاريخ الاستلام")
    if document_date < source.document.document_date:
        raise ValueError("تاريخ الإرجاع لا يمكن أن يكون قبل تاريخ التوزيع")
    supplier = (received_item.supplier_institution or "").strip()
    if not supplier:
        raise ValueError("لا يمكن الإرجاع قبل تحديد الهيئة التي استلم منها الغيار")
    available = returnable_quantity(db, source, exclude)
    if quantity > available:
        raise ValueError(f"الكمية القابلة للإرجاع هي {available} فقط")
    return source, supplier


def _return_received_line(db, received_request_item_id, quantity, document_date, exclude=None):
    quantity = _quantity(quantity)
    item = _item(db, received_request_item_id)
    if not item:
        raise ValueError("بند الاستلام غير موجود")
    received_quantity = Decimal(str(item.received_quantity or 0))
    if received_quantity <= 0:
        raise ValueError("لا يمكن إرجاع بند لم يُستلم")
    receipt = _receipt_date(item)
    if not receipt:
        raise ValueError("لا يمكن الإرجاع قبل تسجيل تاريخ الاستلام")
    if document_date < receipt:
        raise ValueError("تاريخ الإرجاع لا يمكن أن يكون قبل تاريخ الاستلام")
    supplier = (item.supplier_institution or "").strip()
    if not supplier:
        raise ValueError("لا يمكن الإرجاع قبل تحديد الهيئة التي استلم منها الغيار")
    available = available_quantity(db, item, exclude)
    if quantity > available:
        raise ValueError(f"الكمية القابلة للإرجاع هي {available} فقط")
    return item, supplier


def _opts():
    return [
        joinedload(SparePartMovementDocument.items).joinedload(SparePartMovementItem.request_item).joinedload(SparePartRequestItem.spare_part),
        joinedload(SparePartMovementDocument.items).joinedload(SparePartMovementItem.request_item).joinedload(SparePartRequestItem.request).joinedload(SparePartRequest.equipment),
        joinedload(SparePartMovementDocument.source_document).joinedload(SparePartMovementDocument.items),
    ]


def get_document(db, document_id):
    return db.query(SparePartMovementDocument).options(*_opts()).filter(
        SparePartMovementDocument.id == document_id
    ).first()


def _serialize_item(line):
    item = line.request_item
    return {
        "id": line.id, "request_item_id": line.request_item_id,
        "source_item_id": line.source_item_id,
        "received_request_item_id": getattr(line, "received_request_item_id", None),
        "part_name": item.part_name or (item.spare_part.name if item.spare_part else "—"),
        "request_number": item.request.request_number if item.request else None,
        "quantity": line.quantity, "notes": line.notes,
    }


def serialize_document(doc):
    return {
        "id": doc.id, "document_number": doc.document_number,
        "document_type": doc.document_type, "document_date": doc.document_date,
        "issuer": doc.issuer, "recipient": doc.recipient,
        "beneficiary": doc.beneficiary, "notes": doc.notes,
        "source_document_id": doc.source_document_id,
        "items": [_serialize_item(x) for x in doc.items],
    }


def list_documents(db, document_type=None):
    q = db.query(SparePartMovementDocument).options(*_opts())
    if document_type:
        q = q.filter(SparePartMovementDocument.document_type == document_type)
    return [serialize_document(x) for x in q.order_by(
        SparePartMovementDocument.document_date.desc(), SparePartMovementDocument.id.desc()
    ).all()]


def available_register(db, exclude_document_id=None):
    rows = db.query(SparePartRequestItem).join(SparePartRequest).options(
        joinedload(SparePartRequestItem.request).joinedload(SparePartRequest.equipment),
        joinedload(SparePartRequestItem.spare_part),
    ).filter(SparePartRequestItem.received_quantity > 0).order_by(
        SparePartRequest.request_date.desc(), SparePartRequest.id.desc(), SparePartRequestItem.id
    ).all()
    result = []
    for item in rows:
        qty = available_quantity(db, item, exclude_document_id)
        if qty <= 0:
            continue
        result.append({
            "request_item_id": item.id, "request_number": item.request.request_number,
            "part_name": item.part_name or (item.spare_part.name if item.spare_part else "—"),
            "received_quantity": item.received_quantity, "available_quantity": qty,
            "received_date": _receipt_date(item), "supplier_institution": item.supplier_institution or "—",
            "equipment_code": item.request.equipment.asset_code if item.request.equipment else "—",
            "registration_number": item.request.equipment.registration_number if item.request.equipment else "—",
        })
    return result


def return_register(db, exclude_document_id=None):
    rows = db.query(SparePartRequestItem).join(SparePartRequest).options(
        joinedload(SparePartRequestItem.request).joinedload(SparePartRequest.equipment),
        joinedload(SparePartRequestItem.spare_part),
    ).filter(SparePartRequestItem.received_quantity > 0).order_by(
        SparePartRequest.request_date.desc(), SparePartRequest.id.desc(), SparePartRequestItem.id
    ).all()
    balances_by_item = _balances_for(db, rows, exclude_document_id)
    result = []
    for item in rows:
        balances = balances_by_item[item.id]
        received_quantity = balances["received_quantity"]
        distributed_quantity = balances["distributed"]
        returned_quantity = balances["returned"]
        qty = balances["available_for_distribution"]
        if qty <= 0:
            continue
        request = item.request
        equipment = request.equipment
        result.append({
            "request_item_id": item.id,
            "received_request_item_id": item.id,
            "request_number": request.request_number if request else "—",
            "part_name": item.part_name or (item.spare_part.name if item.spare_part else "—"),
            "received_quantity": received_quantity,
            "distributed_quantity": distributed_quantity,
            "returned_quantity": returned_quantity,
            "remaining_quantity": qty,
            "returnable_quantity": qty,
            "balance_status": balances["status"],
            "return_recipient": item.supplier_institution or "—",
            "received_date": _receipt_date(item),
            "equipment": equipment.asset_code if equipment else "—",
            "equipment_code": equipment.asset_code if equipment else "—",
            "registration_number": equipment.registration_number if equipment else "—",
        })
    return result

def _same_ids(lines, attr="request_item_id"):
    ids = [getattr(x, attr) for x in lines]
    if len(ids) != len(set(ids)):
        raise ValueError("لا يمكن تكرار نفس الغيار داخل الوثيقة")


def create_document(db, data: MovementDocumentCreate, user_id=None):
    number = _number(data.document_number)
    _unique_number(db, number)
    if data.document_type == "distribution":
        if not data.recipient:
            raise ValueError("الجهة المستلمة مطلوبة")
        _same_ids(data.items)
        for line in data.items:
            _distribution_line(
                db, line.request_item_id, line.quantity, data.document_date,
                received_request_item_id=line.received_request_item_id,
            )
        obj = SparePartMovementDocument(
            document_number=number, document_type="distribution", document_date=data.document_date,
            issuer=WAREHOUSE_LABEL, recipient=data.recipient, beneficiary=data.recipient,
            notes=data.notes.strip() if data.notes else None, created_by_id=user_id,
        )
    else:
        if not data.items:
            raise ValueError("يجب إضافة بند واحد على الأقل")
        suppliers = set()
        if data.source_document_id is not None:
            raise ValueError("يجب ربط الإرجاع ببند الاستلام وليس بوثيقة توزيع")
        received_ids = []
        for line in data.items:
            received_id = line.received_request_item_id or line.request_item_id
            if line.received_request_item_id and line.request_item_id != received_id:
                raise ValueError("بند الاستلام لا يطابق بند الإرجاع")
            if line.source_item_id is not None:
                raise ValueError("يجب ربط الإرجاع ببند الاستلام وليس ببند توزيع")
            _, supplier = _return_received_line(
                db, received_id, line.quantity, data.document_date
            )
            received_ids.append(received_id)
            suppliers.add(supplier)
        if len(received_ids) != len(set(received_ids)):
            raise ValueError("لا يمكن تكرار نفس الغيار داخل الوثيقة")
        if len(suppliers) != 1:
            raise ValueError("لا يمكن جمع إرجاعات من جهات مستلمة مختلفة في وثيقة واحدة")
        recipient = suppliers.pop()
        obj = SparePartMovementDocument(
            document_number=number, document_type="return", document_date=data.document_date,
            issuer=WAREHOUSE_LABEL, recipient=recipient, beneficiary=recipient,
            notes=data.notes.strip() if data.notes else None,
            source_document_id=None,
            created_by_id=user_id,
        )
    db.add(obj)
    try:
        db.flush()
        for line in data.items:
            request_item_id = line.request_item_id
            source_item_id = line.source_item_id if data.document_type == "return" else None
            received_request_item_id = (
                line.received_request_item_id or line.request_item_id
            )
            if data.document_type == "return" and line.source_item_id:
                source = db.query(SparePartMovementItem).filter(
                    SparePartMovementItem.id == line.source_item_id
                ).first()
                if source:
                    received_request_item_id = source.received_request_item_id or source.request_item_id
            elif data.document_type == "return":
                request_item_id = received_request_item_id
                source_item_id = None
            obj.items.append(SparePartMovementItem(
                request_item_id=request_item_id,
                source_item_id=source_item_id,
                received_request_item_id=received_request_item_id,
                quantity=line.quantity, notes=line.notes.strip() if line.notes else None,
            ))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if "document_number" in str(getattr(exc, "orig", exc)):
            raise ValueError(DOCUMENT_NUMBER_TAKEN) from exc
        raise
    return get_document(db, obj.id)


def update_document(db, document_id, data: MovementDocumentUpdate, user_id=None):
    obj = get_document(db, document_id)
    if not obj:
        raise ValueError("وثيقة الغيار غير موجودة")
    number = _number(data.document_number) if data.document_number is not None else obj.document_number
    _unique_number(db, number, obj.id)
    document_date = data.document_date or obj.document_date

    if obj.document_type == "distribution":
        if obj.return_documents:
            raise ValueError("لا يمكن تعديل توزيع له إرجاع مرتبط؛ صحح الإرجاع أولاً")
        recipient = data.recipient or obj.recipient
        if not recipient:
            raise ValueError("الجهة المستلمة مطلوبة")
        lines = data.items if data.items is not None else obj.items
        _same_ids(lines)
        for line in lines:
            _distribution_line(
                db, line.request_item_id, line.quantity, document_date, obj.id,
                received_request_item_id=line.received_request_item_id,
            )
        obj.document_number, obj.document_date = number, document_date
        obj.recipient, obj.beneficiary = recipient, recipient
        if data.notes is not None:
            obj.notes = data.notes.strip() or None
        if data.items is not None:
            obj.items.clear()
            db.flush()
            for line in data.items:
                obj.items.append(SparePartMovementItem(
                    request_item_id=line.request_item_id,
                    received_request_item_id=line.request_item_id,
                    quantity=line.quantity,
                    notes=line.notes,
                ))
    else:
        lines = data.items if data.items is not None else obj.items
        if not lines:
            raise ValueError("يجب إضافة بند واحد على الأقل")
        suppliers = set()
        received_ids = []
        for line in lines:
            received_id = getattr(line, "received_request_item_id", None) or line.request_item_id
            if getattr(line, "received_request_item_id", None) and line.request_item_id != received_id:
                raise ValueError("بند الاستلام لا يطابق بند الإرجاع")
            _, supplier = _return_received_line(
                db, received_id, line.quantity, document_date, obj.id
            )
            received_ids.append(received_id)
            suppliers.add(supplier)
        if len(received_ids) != len(set(received_ids)):
            raise ValueError("لا يمكن تكرار نفس الغيار داخل الوثيقة")
        if len(suppliers) != 1:
            raise ValueError("لا يمكن جمع إرجاعات من جهات مستلمة مختلفة في وثيقة واحدة")
        recipient = suppliers.pop()
        obj.document_number, obj.document_date = number, document_date
        obj.source_document_id = None
        obj.issuer, obj.recipient, obj.beneficiary = WAREHOUSE_LABEL, recipient, recipient
        if data.notes is not None:
            obj.notes = data.notes.strip() or None
        obj.items.clear()
        db.flush()
        for line, received_id in zip(lines, received_ids):
            obj.items.append(SparePartMovementItem(
                request_item_id=received_id,
                source_item_id=None,
                received_request_item_id=received_id,
                quantity=line.quantity,
                notes=line.notes,
            ))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if "document_number" in str(getattr(exc, "orig", exc)):
            raise ValueError(DOCUMENT_NUMBER_TAKEN) from exc
        raise
    return get_document(db, obj.id)


def _document_deletion_lines(db, obj):
    """Return the selected document lines and return lines owned by it."""
    lines = list(obj.items)
    dependent_returns = []
    if obj.document_type == "distribution" and lines:
        distribution_line_ids = [line.id for line in lines]
        dependent_returns = db.query(SparePartMovementItem).join(
            SparePartMovementDocument
        ).filter(
            SparePartMovementDocument.document_type == "return",
            or_(
                SparePartMovementItem.source_item_id.in_(distribution_line_ids),
                SparePartMovementDocument.source_document_id == obj.id,
            ),
        ).all()
    return lines, dependent_returns


def delete_document_impact(db, document_id):
    """Describe the selected document and dependent movements that will be removed."""
    obj = get_document(db, document_id)
    if not obj:
        raise ValueError("وثيقة الغيار غير موجودة")
    lines, dependent_returns = _document_deletion_lines(db, obj)
    effects = []
    for line in lines:
        name = line.request_item.part_name if line.request_item else f"بند الطلب #{line.request_item_id}"
        effects.append({"label": f"{name}: الكمية {line.quantity}", "count": 1})
    dependent_doc_ids = {line.document_id for line in dependent_returns}
    dependent_docs = db.query(SparePartMovementDocument).filter(
        SparePartMovementDocument.id.in_(dependent_doc_ids)
    ).all() if dependent_doc_ids else []
    docs_by_id = {doc.id: doc for doc in dependent_docs}
    full_docs = sum(
        sum(line.document_id == doc_id for line in dependent_returns) == len(docs_by_id[doc_id].items)
        for doc_id in dependent_doc_ids
    )
    if dependent_returns:
        effects.append({"label": "بنود الإرجاع التابعة التي ستحذف", "count": len(dependent_returns)})
        effects.append({"label": "وثائق الإرجاع التي ستحذف بالكامل", "count": full_docs})
        effects.append({"label": "وثائق الإرجاع المشتركة التي ستبقى ببنودها الأخرى", "count": len(dependent_doc_ids) - full_docs, "kind": "remain"})
    if obj.document_type == "distribution":
        effects.append({"label": "إجمالي الكمية التي ستعود إلى الرصيد المتاح", "count": _sum(line.quantity for line in obj.items)})
    else:
        effects.append({"label": "إجمالي الكمية المرتجعة التي ستلغى", "count": _sum(line.quantity for line in obj.items)})
        affected_item_ids = {line.received_request_item_id or line.request_item_id for line in lines}
        for item_id in affected_item_ids:
            item = db.query(SparePartRequestItem).filter(SparePartRequestItem.id == item_id).first()
            if item is None:
                continue
            balance = _compute_balances(db, item, exclude=obj.id)
            if balance["status"].startswith("invalid_"):
                effects.append({
                    "label": "تنبيه: بعد حذف هذا الإرجاع سيظهر رصيد غير صالح؛ راجع سجل الحركات قبل أي توزيع جديد",
                    "count": 1,
                    "kind": "warning",
                })
    return {"label": obj.document_number, "effects": effects, "blocked": None}


def delete_document(db, document_id):
    obj = get_document(db, document_id)
    if not obj:
        raise ValueError("وثيقة الغيار غير موجودة")
    _, dependent_returns = _document_deletion_lines(db, obj)
    affected_document_ids = {line.document_id for line in dependent_returns}
    dependent_doc_ids = db.query(SparePartMovementDocument.id).filter(
        SparePartMovementDocument.document_type == "return",
        SparePartMovementDocument.source_document_id == obj.id,
    ).all() if obj.document_type == "distribution" else []
    affected_document_ids.update(row[0] for row in dependent_doc_ids)
    for line in dependent_returns:
        if line in line.document.items:
            line.document.items.remove(line)
        else:
            db.delete(line)
    db.flush()
    for dependent_document_id in affected_document_ids:
        dependent_document = db.query(SparePartMovementDocument).filter(
            SparePartMovementDocument.id == dependent_document_id
        ).first()
        has_remaining_items = db.query(SparePartMovementItem.id).filter(
            SparePartMovementItem.document_id == dependent_document_id
        ).first()
        if dependent_document is not None and not has_remaining_items:
            db.delete(dependent_document)
    db.delete(obj)
    db.commit()


def request_item_movement_deletion_plan(db, request_item_ids):
    """Return the exact movement rows and documents owned by request items.

    This read-only plan is shared by deletion preview and execution so the UI
    cannot promise a different impact from the one the service applies.
    """
    request_item_ids = {int(value) for value in request_item_ids}
    if not request_item_ids:
        return {"lines": [], "documents": [], "documents_to_delete": []}
    distribution_lines = db.query(SparePartMovementItem).join(
        SparePartMovementDocument
    ).filter(
        SparePartMovementDocument.document_type == "distribution",
        or_(SparePartMovementItem.request_item_id.in_(request_item_ids),
            SparePartMovementItem.received_request_item_id.in_(request_item_ids)),
    ).all()
    distribution_line_ids = {line.id for line in distribution_lines}
    return_filters = [
        SparePartMovementItem.request_item_id.in_(request_item_ids),
        SparePartMovementItem.received_request_item_id.in_(request_item_ids),
    ]
    if distribution_line_ids:
        return_filters.append(SparePartMovementItem.source_item_id.in_(distribution_line_ids))
    distribution_lines_per_document = {}
    for line in distribution_lines:
        distribution_lines_per_document[line.document_id] = distribution_lines_per_document.get(line.document_id, 0) + 1
    fully_removed_distribution_document_ids = set()
    for document_id, selected_line_count in distribution_lines_per_document.items():
        total_line_count = db.query(SparePartMovementItem.id).filter(
            SparePartMovementItem.document_id == document_id
        ).count()
        if total_line_count == selected_line_count:
            fully_removed_distribution_document_ids.add(document_id)
    if fully_removed_distribution_document_ids:
        legacy_return_document_ids = db.query(SparePartMovementDocument.id).filter(
            SparePartMovementDocument.document_type == "return",
            SparePartMovementDocument.source_document_id.in_(fully_removed_distribution_document_ids),
        ).all()
        return_filters.append(SparePartMovementItem.document_id.in_([row[0] for row in legacy_return_document_ids]))
    return_lines = db.query(SparePartMovementItem).join(
        SparePartMovementDocument
    ).filter(
        SparePartMovementDocument.document_type == "return",
        or_(*return_filters),
    ).all()
    # Older returns linked only by source_document_id. If every distribution
    # line in a document is being removed, those legacy return documents also
    # belong to the deleted request's movement chain.
    affected_lines = {line.id: line for line in distribution_lines + return_lines}
    affected_document_ids = {line.document_id for line in affected_lines.values()}
    documents = db.query(SparePartMovementDocument).filter(
        SparePartMovementDocument.id.in_(affected_document_ids)
    ).all() if affected_document_ids else []
    lines_by_document = {}
    for line in affected_lines.values():
        lines_by_document.setdefault(line.document_id, set()).add(line.id)
    documents_to_delete = [
        document for document in documents
        if len(lines_by_document.get(document.id, set())) == len(document.items)
    ]
    return {
        "lines": list(affected_lines.values()),
        "documents": documents,
        "documents_to_delete": documents_to_delete,
    }


def delete_movements_for_request_items(db, request_item_ids):
    """Remove movements owned by request items without committing the caller's transaction."""
    plan = request_item_movement_deletion_plan(db, request_item_ids)
    for line in plan["lines"]:
        db.delete(line)
    db.flush()
    deleted_documents = 0
    for document in plan["documents"]:
        db.expire(document, ["items"])
        if not document.items:
            db.delete(document)
            deleted_documents += 1
    db.flush()
    remaining = db.query(SparePartMovementItem.id).filter(or_(
        SparePartMovementItem.request_item_id.in_(request_item_ids),
        SparePartMovementItem.received_request_item_id.in_(request_item_ids),
    )).first()
    if remaining:
        raise ValueError("تعذر حذف جميع حركات الغيار المرتبطة؛ أُلغي حذف الطلب للمحافظة على سلامة السجلات")
    return {
        "movement_lines_deleted": len(plan["lines"]),
        "movement_documents_deleted": deleted_documents,
    }


def history(db, request_item_id):
    item = db.query(SparePartRequestItem).options(
        joinedload(SparePartRequestItem.request).joinedload(SparePartRequest.fault),
        joinedload(SparePartRequestItem.request).joinedload(SparePartRequest.repair).joinedload(Repair.fault),
        joinedload(SparePartRequestItem.request).joinedload(SparePartRequest.equipment),
        joinedload(SparePartRequestItem.spare_part),
    ).filter(SparePartRequestItem.id == request_item_id).first()
    if not item:
        raise ValueError("بند الغيار غير موجود")
    req = item.request
    source = req.fault if req.source_type == "fault" else (req.repair.fault if req.repair else None)
    docs = db.query(SparePartMovementDocument).join(SparePartMovementItem).filter(
        or_(
            SparePartMovementItem.request_item_id == request_item_id,
            SparePartMovementItem.received_request_item_id == request_item_id,
        )
    ).order_by(SparePartMovementDocument.document_date.asc(), SparePartMovementDocument.id.asc()).all()
    return {
        "item": {
            "id": item.id, "part_name": item.part_name or (item.spare_part.name if item.spare_part else "—"),
            "requested_quantity": item.requested_quantity, "received_quantity": item.received_quantity,
            "received_date": _receipt_date(item), "recipient": item.recipient,
            "supplier_institution": item.supplier_institution,
        },
        "request": {
            "id": req.id, "number": req.request_number, "date": req.request_date,
            "status": req.status, "source_type": req.source_type,
            "source_id": req.fault_id if req.source_type == "fault" else req.repair_id,
            "report_number": source.report_number if source else None,
            "reason": source.description if source else req.notes,
            "notes": req.notes,
            "equipment": {
                "asset_code": req.equipment.asset_code if req.equipment else None,
                "registration_number": req.equipment.registration_number if req.equipment else None,
            },
        },
        "movements": [serialize_document(d) for d in docs],
        "balances": _compute_balances(db, item),
    }
