from contextlib import contextmanager

from sqlalchemy.exc import IntegrityError
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.modules.faults_repairs.models import Fault, Repair, SparePart
from .models import SparePartRequest, SparePartRequestItem
from .schemas import SparePartRequestCreate, SparePartRequestItemCreate, SparePartRequestItemUpdate, SparePartRequestStatusUpdate, SparePartRequestUpdate
from app.modules.spare_parts_movements.models import SparePartMovementDocument, SparePartMovementItem

RECEIPT_BEFORE_REQUEST = "تاريخ الاستلام لا يمكن أن يكون قبل تاريخ الطلب."
RECEIPT_CONFLICT = "طلب الغيار هذا له تاريخ استلام واحد. افتح طلب غيار جديد للاستلام الجديد."
REQUEST_NUMBER_TAKEN = "رقم الطلب مستخدم مسبقًا، يرجى إدخال رقم آخر."


def _request_number(value: str | None) -> str:
    """رقم الطلب نصٌّ حرّ: عدّة أرقام ورموز وحروف، ويبقى كما كتبه المستخدم.

    تُزال المسافات الطرفية وحدها: أحد المدخلين يقليم الرقم (رأس الطلب)
    والآخر لا (نموذج الإنشاء)، فكانت « NB-1 » و«NB-1» تُحفظان معاً بلا أن
    يراهما الفحص متساويتين. لا نمسّ الأحرف ولا حالة الأحرف ولا الرموز:
    «70001/26» و«NB-1-A» يبقىان كما هما.
    """
    number = (value or "").strip()
    if not number:
        raise ValueError("رقم الطلب مطلوب")
    return number


def _check_request_number_free(db: Session, request_number: str, exclude_id: int | None = None):
    """رقم طلب الغيار فريد تماماً: لا طلبان بالرقم نفسه.

    `exclude_id` يستثنى الطلب المعدَّل نفسه، فيحتفظ برقمه ويمنع فقط
    أخذه رقمُ طلبٍ آخر.
    """
    query = db.query(SparePartRequest.id).filter(
        SparePartRequest.request_number == request_number
    )
    if exclude_id is not None:
        query = query.filter(SparePartRequest.id != exclude_id)
    if query.first():
        raise ValueError(REQUEST_NUMBER_TAKEN)


def _duplicate_number(exc: IntegrityError) -> bool:
    """هل تعذّر الحفظ بسبب تكرار رقم الطلب وحده؟"""
    message = str(getattr(exc, "orig", exc))
    return "request_number" in message and "UNIQUE" in message.upper()


@contextmanager
def _no_raw_sql(db: Session):
    """يترجم تكرار رقم الطلب إلى رسالة مفهومة بدل خطأ SQL خام للمستخدم.

    الفحص المسبق في `_check_request_number_free` وحده لا يكفي: طلبان
    يصلان في اللحظة نفسها يمرّان به معاً، فيرفض الثاني القيدَ في القاعدة
    عند الحفظ لا عند الفحص. خطأ قاعدة البيانات لا يمرّ إلى المستخدم أبداً.
    """
    try:
        yield
    except IntegrityError as exc:
        db.rollback()
        if _duplicate_number(exc):
            raise ValueError(REQUEST_NUMBER_TAKEN) from exc
        raise


def _check_receipt_date(request_date, received_date):
    """تاريخ الاستلام اختياري، لكن إن أُدخل فلا يسبق تاريخ الطلب.

    تاريخ الطلب هو المرجع لإنشاء الطلب، ولا يصحّ أن يُستلم قبله.
    """
    if received_date is not None and request_date is not None and received_date < request_date:
        raise ValueError(RECEIPT_BEFORE_REQUEST)


def _receipt_conflicts(request, received_date):
    """هل يخالف التاريخ المُرسل تاريخ استلام الطلب القائم؟"""
    if received_date is None or request.received_date is None:
        return False
    return received_date != request.received_date


def _store_receipt_date(request, received_date):
    """تخزين تاريخ استلام الطلب على الطلب ونقله إلى كل بنوده.

    الطلب يُستلم مرة واحدة، فلا معنى لتاريخ مختلف بين بنوده.
    """
    request.received_date = received_date
    for item in request.items:
        item.received_date = received_date


def _source(db: Session, source_type: str, source_id: int):
    if source_type == "fault":
        obj = db.query(Fault).options(joinedload(Fault.equipment)).filter(Fault.id == source_id).first()
        if not obj:
            raise ValueError("العطل غير موجود")
        return obj, obj.equipment_id, obj.reported_date
    obj = db.query(Repair).options(joinedload(Repair.fault).joinedload(Fault.equipment)).filter(Repair.id == source_id).first()
    if not obj:
        raise ValueError("التصليح غير موجود")
    return obj, obj.fault.equipment_id if obj.fault else None, obj.repair_date


def _resolve_part(db: Session, part_id: int | None, name: str | None):
    """يبني (spare_part_id, part_name) من رابط اختياري بالمخزون واسم حر.

    الربط بالمخزون اختياري: إن اختير من المكتبة يُربط ويُشتق منه الاسم عند
    عدم تمرير اسم، وإن لم يُختَر يُحفظ الاسم الحر وحده دون مطابقة حرفية
    بسجل قطع الغيار (المطابقة الحرفية هي ما كان تمنع الاسم الحر أصلاً).
    """
    part_id = part_id if part_id else None
    name = (name or "").strip() or None
    if part_id:
        part = db.query(SparePart).filter(SparePart.id == part_id).first()
        if not part:
            raise ValueError("قطعة الغيار غير موجودة")
        return part.id, name or part.name
    if not name:
        raise ValueError("اسم قطعة الغيار مطلوب")
    return None, name


def _item_identity(part_id: int | None, part_name: str | None):
    """معرّف منع التكرار: المعرّف المرجعي إن وُجد، وإلا الاسم الحرّ."""
    return ("id", part_id) if part_id else ("name", (part_name or "").strip().casefold())


def serialize_item(item):
    # تاريخ الاستلام واحد للطلب كله، فهو خاصية الطلب لا البند: لذلك يُعرض على
    # كل بنوده حتى الذي لم يُستلم بعد. ولا حاجة لعمَل موازٍ هنا: التاريخ يُمسح
    # من الترويسة عند التراجع عن آخر استلام.
    return {
        "id": item.id,
        "spare_part_id": item.spare_part_id,
        "part_name": item.part_name or (item.spare_part.name if item.spare_part else None),
        "requested_quantity": item.requested_quantity,
        "received_quantity": item.received_quantity,
        "received_date": item.request.received_date or item.received_date,
        "recipient": item.recipient,
        "supplier_institution": item.supplier_institution,
        "notes": item.notes,
    }


def serialize_request(obj):
    report_number = None
    if obj.source_type == "fault" and obj.fault:
        report_number = obj.fault.report_number
    elif obj.source_type == "repair" and obj.repair:
        report_number = obj.repair.fault.report_number if obj.repair.fault else obj.repair.repair_document
    return {
        "id": obj.id,
        "request_number": obj.request_number,
        "request_date": obj.request_date,
        "received_date": obj.received_date,
        "source_type": obj.source_type,
        "fault_id": obj.fault_id,
        "repair_id": obj.repair_id,
        "equipment_id": obj.equipment_id,
        "status": obj.status,
        "notes": obj.notes,
        "equipment_code": obj.equipment.asset_code if obj.equipment else None,
        "equipment_registration": obj.equipment.registration_number if obj.equipment else None,
        "report_number": report_number,
        "items": [serialize_item(i) for i in obj.items],
    }


def create_request(db: Session, data: SparePartRequestCreate, user_id: int | None = None):
    number = _request_number(data.request_number)
    _check_request_number_free(db, number)
    _, equipment_id, source_date = _source(db, data.source_type, data.source_id)
    existing = db.query(SparePartRequest).filter(
        SparePartRequest.fault_id == (data.source_id if data.source_type == "fault" else None),
        SparePartRequest.repair_id == (data.source_id if data.source_type == "repair" else None),
    ).first()
    if existing:
        raise ValueError("يوجد طلب غيار مرتبط بهذا المصدر بالفعل")
    if data.request_date != source_date:
        raise ValueError("تاريخ الطلب يجب أن يطابق تاريخ المصدر")

    # تاريخ استلام واحد للطلب: إمّا على الطلب، أو على بنوده فكلها تتطابق.
    dates = {item.received_date for item in data.items if item.received_date}
    if data.received_date:
        dates.add(data.received_date)
    if len(dates) > 1:
        raise ValueError(RECEIPT_CONFLICT)
    receipt_date = next(iter(dates), None)
    _check_receipt_date(data.request_date, receipt_date)

    resolved = [
        _resolve_part(db, item.spare_part_id, item.part_name)
        for item in data.items
    ]
    identities = [_item_identity(part_id, part_name) for part_id, part_name in resolved]
    if len(identities) != len(set(identities)):
        raise ValueError("لا يمكن تكرار قطعة الغيار داخل الطلب")

    obj = SparePartRequest(
        request_number=number,
        request_date=data.request_date,
        received_date=receipt_date,
        source_type=data.source_type,
        fault_id=data.source_id if data.source_type == "fault" else None,
        repair_id=data.source_id if data.source_type == "repair" else None,
        equipment_id=equipment_id,
        status="pending",
        requested_by_id=user_id,
        notes=data.notes,
    )
    db.add(obj)
    with _no_raw_sql(db):
        db.flush()
    for item, (part_id, part_name) in zip(data.items, resolved):
        values = item.model_dump(exclude={"spare_part_id", "part_name"})
        values["received_date"] = receipt_date
        obj.items.append(
            SparePartRequestItem(
                **values,
                spare_part_id=part_id,
                part_name=part_name,
            )
        )
    with _no_raw_sql(db):
        db.commit()
    return get_request(db, obj.id)


def update_request(db: Session, obj: SparePartRequest, data: SparePartRequestUpdate):
    if obj.status != "pending":
        raise ValueError("لا يمكن تعديل طلب إلا وهو قيد الانتظار")
    values = data.model_dump(exclude_unset=True)
    if "request_number" in values:
        number = _request_number(values["request_number"])
        _check_request_number_free(db, number, obj.id)
        values["request_number"] = number
    if "request_date" in values:
        _, _, source_date = _source(db, obj.source_type, obj.fault_id or obj.repair_id)
        if values["request_date"] != source_date:
            raise ValueError("تاريخ الطلب يجب أن يطابق تاريخ المصدر")
    # فحص واحد يغطّي تغيير التاريخين معاً أو أحدهما: المقارنة دائماً بين
    # التاريخ الجديد وتاريخ الطلب المرجعي، فلا يُتحقَّق من نفس القارنة مرتين.
    if "request_date" in values or "received_date" in values:
        _check_receipt_date(
            values.get("request_date", obj.request_date),
            values.get("received_date", obj.received_date),
        )
    if "received_date" in values and values["received_date"] != obj.received_date:
        _store_receipt_date(obj, values["received_date"])
    for key, value in values.items():
        setattr(obj, key, value)
    with _no_raw_sql(db):
        db.commit()
    return get_request(db, obj.id)


def delete_request(db: Session, obj: SparePartRequest):
    if obj.status == "approved":
        raise ValueError(
            "لا يمكن حذف طلب معتمد، فهو وثيقة معتمدة. غيّر الحالة إلى «ملغى» أو «مرفوض»."
        )
    if any(item.received_quantity > 0 for item in obj.items):
        raise ValueError(
            "لا يمكن حذف طلب تم تسجيل استلام فيه: الكميات المستلمة جزء من سجل "
            "الاستلام ولا يمكن التراجع عنها. إن كان الاستلام خطأً فتراجع عنه بنداً بنداً "
            "من زر «تراجع عن الاستلام»؛ وإن كان صحيحاً فغيّر الحالة إلى «ملغى»."
        )
    db.delete(obj)
    db.commit()


def add_item(db: Session, request_id: int, data: SparePartRequestItemCreate):
    request = get_request(db, request_id)
    if not request:
        raise ValueError("طلب الغيار غير موجود")
    if request.status not in {"pending", "approved"}:
        raise ValueError("لا يمكن إضافة بند إلا لطلب قيد الانتظار أو معتمد")
    _check_receipt_date(request.request_date, data.received_date)
    if _receipt_conflicts(request, data.received_date):
        raise ValueError(RECEIPT_CONFLICT)
    if data.received_date and request.received_date is None:
        _store_receipt_date(request, data.received_date)
    part_id, part_name = _resolve_part(db, data.spare_part_id, data.part_name)
    identity = _item_identity(part_id, part_name)
    for existing in request.items:
        if _item_identity(existing.spare_part_id, existing.part_name) == identity:
            raise ValueError("قطعة الغيار موجودة بالفعل في الطلب")
    if data.received_quantity > 0 and (not data.received_date or not data.recipient or not data.supplier_institution):
        raise ValueError("عند تسجيل استلام يجب إدخال تاريخ الاستلام والمستلم والمؤسسة الممونة")
    values = data.model_dump(exclude={"part_name", "spare_part_id"})
    # بند الطلب الجديد يشارك تاريخ استلام الطلب، لا تاريخاً خاصاً به.
    values["received_date"] = request.received_date
    item = SparePartRequestItem(
        request_id=request_id,
        spare_part_id=part_id,
        part_name=part_name,
        **values,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def update_item(db: Session, item: SparePartRequestItem, data: SparePartRequestItemUpdate):
    if item.request.status == "cancelled":
        raise ValueError("لا يمكن تعديل طلب ملغى")
    values = data.model_dump(exclude_unset=True)
    touches_assignment = any(k in values for k in ("spare_part_id", "part_name", "requested_quantity"))
    if touches_assignment and item.request.status != "pending":
        raise ValueError("لا يمكن تعديل التعيين أو الكمية المطلوبة إلا لطلب قيد الانتظار")
    if item.received_quantity > 0 and touches_assignment:
        raise ValueError("لا يمكن تعديل التعيين أو الكمية المطلوبة بعد تسجيل الاستلام")
    if "spare_part_id" in values or "part_name" in values:
        part_id, part_name = _resolve_part(
            db,
            values.get("spare_part_id", item.spare_part_id),
            values.get("part_name", item.part_name),
        )
        identity = _item_identity(part_id, part_name)
        for other in item.request.items:
            if other.id != item.id and _item_identity(other.spare_part_id, other.part_name) == identity:
                raise ValueError("قطعة الغيار موجودة بالفعل في الطلب")
        values["spare_part_id"] = part_id
        values["part_name"] = part_name
    if "received_date" in values:
        _check_receipt_date(item.request.request_date, values["received_date"])
        if _receipt_conflicts(item.request, values["received_date"]):
            raise ValueError(RECEIPT_CONFLICT)
    for key, value in values.items():
        setattr(item, key, value)
    if "received_date" in values and values["received_date"] != item.request.received_date:
        _store_receipt_date(item.request, values["received_date"])
    if item.received_quantity > 0 and (not item.received_date or not item.recipient or not item.supplier_institution):
        raise ValueError("عند تسجيل استلام يجب إدخال تاريخ الاستلام والمستلم والمؤسسة الممونة")
    db.commit()
    db.refresh(item)
    return item


def delete_item(db: Session, item: SparePartRequestItem):
    if item.received_quantity > 0:
        raise ValueError(
            "لا يمكن حذف بند تم تسجيل استلام له. إن كان الاستلام خطأً فاستخدم "
            "«تراجع عن الاستلام» على البند."
        )
    if item.request.status != "pending":
        raise ValueError("لا يمكن حذف بند إلا من طلب قيد الانتظار")
    db.delete(item)
    db.commit()


def undo_item_receipt(db: Session, item: SparePartRequestItem):
    """يلغي استلام بند سُجّل بالخطأ.

    الاستلام واقعة موثّقة في سجل الاستلام، فلا يُلغى إلا ما دام الطلب قيد
    الانتظار: بعد القبول أو الإلغاء يصبح السجل نهائياً. التصفير يفضي أيضاً
    إلى فتح الحذف، فيجب أن يكون قراراً صريحاً لا نتيجةً جانبية.
    """
    if item.request.status != "pending":
        raise ValueError(
            "لا يمكن التراجع عن الاستلام إلا لطلب قيد الانتظار؛ السجل نهائي بعد تغيير الحالة."
        )
    if item.received_quantity <= 0:
        raise ValueError("لا يوجد استلام مسجل لهذا البند")
    item.received_quantity = 0
    item.received_date = None
    item.recipient = None
    item.supplier_institution = None
    # تاريخ الاستلام في الترويسة مشترك بين البنود، فلا يبقى بلا معنى بعد آخر بند
    if not any(other.received_quantity > 0 for other in item.request.items):
        item.request.received_date = None
    db.commit()
    db.refresh(item)
    return item


def update_status(db: Session, obj: SparePartRequest, data: SparePartRequestStatusUpdate):
    obj.status = data.status
    db.commit()
    db.refresh(obj)
    return serialize_request(get_request(db, obj.id))


def list_requests(db: Session, status=None, source_type=None):
    q = db.query(SparePartRequest).options(
        joinedload(SparePartRequest.items).joinedload(SparePartRequestItem.spare_part),
        joinedload(SparePartRequest.equipment),
        joinedload(SparePartRequest.fault),
        joinedload(SparePartRequest.repair).joinedload(Repair.fault),
    )
    if status:
        q = q.filter(SparePartRequest.status == status)
    if source_type:
        q = q.filter(SparePartRequest.source_type == source_type)
    return [serialize_request(x) for x in q.order_by(SparePartRequest.request_date.desc(), SparePartRequest.id.desc()).all()]


def get_request(db: Session, request_id: int):
    return db.query(SparePartRequest).options(
        joinedload(SparePartRequest.items).joinedload(SparePartRequestItem.spare_part),
        joinedload(SparePartRequest.equipment),
        joinedload(SparePartRequest.fault),
        joinedload(SparePartRequest.repair).joinedload(Repair.fault),
    ).filter(SparePartRequest.id == request_id).first()


def received_register(db: Session):
    """سجل الغيار المستلم، ومع كل بند رصيده وحالته.

    الأرصدة تُحسب من نفس دالة الحركة التي تقرأ منها صفحة التوزيع، فالسجل
    يعرض ما ستعرضه الصفحات الأخرى للبند نفسه بلا اختلاف. وتُحسب لكل البنود
    في ثلاثة استعلامات، لا ثلاثة استعلامات لكل بند.
    """
    from app.modules.spare_parts_movements import services as movement_services

    rows = db.query(SparePartRequestItem).join(SparePartRequest).options(
        joinedload(SparePartRequestItem.spare_part),
        joinedload(SparePartRequestItem.request).joinedload(SparePartRequest.equipment),
        joinedload(SparePartRequestItem.request).joinedload(SparePartRequest.fault),
        joinedload(SparePartRequestItem.request).joinedload(SparePartRequest.repair).joinedload(Repair.fault),
    ).filter(SparePartRequestItem.received_quantity > 0).order_by(
        SparePartRequest.request_date.desc(), SparePartRequest.id.desc(), SparePartRequestItem.id
    ).all()

    balances_by_item = movement_services._balances_for(db, rows)

    # آخر حركة فعلية للبند: توزيع أو إرجاع. الاستلام ليس وثيقة حركة في
    # وحدة الحركة، لذلك يبقى الاستلام هو الحالة الافتراضية عند عدم وجود حركة.
    item_ids = [item.id for item in rows]
    latest_by_item = {}
    if item_ids:
        movement_rows = (
            db.query(
                SparePartMovementItem.request_item_id,
                SparePartMovementItem.received_request_item_id,
                SparePartMovementDocument.document_type,
                SparePartMovementDocument.document_date,
                SparePartMovementDocument.document_number,
                SparePartMovementDocument.id,
            )
            .join(
                SparePartMovementDocument,
                SparePartMovementItem.document_id == SparePartMovementDocument.id,
            )
            .filter(
                or_(
                    SparePartMovementItem.request_item_id.in_(item_ids),
                    SparePartMovementItem.received_request_item_id.in_(item_ids),
                )
            )
            .order_by(
                SparePartMovementDocument.document_date.desc(),
                SparePartMovementDocument.created_at.desc(),
                SparePartMovementDocument.id.desc(),
            )
            .all()
        )
        for row in movement_rows:
            latest_by_item.setdefault(row[0], row)
            if row[1] is not None:
                latest_by_item.setdefault(row[1], row)

    result = []
    for item in rows:
        req = item.request
        balances = balances_by_item[item.id]
        result.append({
            "request_item_id": item.id,
            "request_number": req.request_number,
            "part_name": item.part_name or (item.spare_part.name if item.spare_part else "—"),
            "requested_quantity": item.requested_quantity,
            "received_date": req.received_date or item.received_date,
            "equipment": {
                "asset_code": req.equipment.asset_code if req.equipment else "—",
            },
            "registration_number": req.equipment.registration_number if req.equipment else "—",
            "recipient": item.recipient or "—",
            "supplier_institution": item.supplier_institution or "—",
            # الأرصدة من نفس دالة الحركة التي تقرأ منها صفحتا التوزيع
            # والإرجاع، فلا يختلف رقمان للبند نفسه بين صفحة وصفحة
            "received_quantity": balances["received_quantity"],
            "distributed": balances["distributed"],
            "returned": balances["returned"],
            "available_for_distribution": balances["available_for_distribution"],
            "remaining_with_entity": balances["remaining_with_entity"],
            "status": balances["status"],
            "last_movement_type": (
                latest_by_item[item.id][2]
                if item.id in latest_by_item
                else "receipt"
            ),
            "last_movement_date": (
                latest_by_item[item.id][3]
                if item.id in latest_by_item
                else item.received_date or req.received_date
            ),
            "last_movement_document_number": (
                latest_by_item[item.id][4] if item.id in latest_by_item else None
            ),
        })
    return result


def source_options(db: Session, source_type: str):
    if source_type == "fault":
        rows = db.query(Fault).options(joinedload(Fault.equipment)).order_by(Fault.reported_date.desc(), Fault.id.desc()).limit(200).all()
        return [{
            "id": x.id,
            "date": x.reported_date.isoformat(),
            "report_number": x.report_number or "—",
            "registration_number": x.equipment.registration_number if x.equipment else "—",
        } for x in rows]

    rows = db.query(Repair).options(joinedload(Repair.fault).joinedload(Fault.equipment)).order_by(Repair.repair_date.desc(), Repair.id.desc()).limit(200).all()
    return [{
        "id": x.id,
        "date": x.repair_date.isoformat(),
        "report_number": x.fault.report_number if x.fault and x.fault.report_number else (x.repair_document or "—"),
        "registration_number": x.fault.equipment.registration_number if x.fault and x.fault.equipment else "—",
    } for x in rows]


def pending_count(db: Session):
    return db.query(SparePartRequest).filter(SparePartRequest.status == "pending").count()
