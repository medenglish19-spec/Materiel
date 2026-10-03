from sqlalchemy.orm import Session, joinedload

from app.modules.faults_repairs.models import Fault, Repair, SparePart
from .models import SparePartRequest, SparePartRequestItem
from .schemas import SparePartRequestCreate, SparePartRequestItemCreate, SparePartRequestItemUpdate, SparePartRequestStatusUpdate, SparePartRequestUpdate


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


def _serialize(item):
    return {
        "id": item.id,
        "spare_part_id": item.spare_part_id,
        "part_name": item.spare_part.name if item.spare_part else None,
        "requested_quantity": item.requested_quantity,
        "received_quantity": item.received_quantity,
        "received_date": item.received_date,
        "recipient": item.recipient,
        "supplier_institution": item.supplier_institution,
        "notes": item.notes,
        "part_name": item.spare_part.name if item.spare_part else None,
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
        "source_type": obj.source_type,
        "fault_id": obj.fault_id,
        "repair_id": obj.repair_id,
        "equipment_id": obj.equipment_id,
        "status": obj.status,
        "notes": obj.notes,
        "equipment_code": obj.equipment.asset_code if obj.equipment else None,
        "equipment_registration": obj.equipment.registration_number if obj.equipment else None,
        "report_number": report_number,
        "items": [_serialize(i) for i in obj.items],
    }


def create_request(db: Session, data: SparePartRequestCreate, user_id: int | None = None):
    if db.query(SparePartRequest).filter(SparePartRequest.request_number == data.request_number).first():
        raise ValueError("رقم وثيقة الطلب مستخدم مسبقًا")
    _, equipment_id, source_date = _source(db, data.source_type, data.source_id)
    existing = db.query(SparePartRequest).filter(
        SparePartRequest.fault_id == (data.source_id if data.source_type == "fault" else None),
        SparePartRequest.repair_id == (data.source_id if data.source_type == "repair" else None),
    ).first()
    if existing:
        raise ValueError("يوجد طلب غيار مرتبط بهذا المصدر بالفعل")
    if data.request_date != source_date:
        raise ValueError("تاريخ الطلب يجب أن يطابق تاريخ المصدر")

    part_ids = [x.spare_part_id for x in data.items]
    if len(part_ids) != len(set(part_ids)):
        raise ValueError("لا يمكن تكرار قطعة الغيار داخل الطلب")
    if part_ids:
        parts = {p.id for p in db.query(SparePart).filter(SparePart.id.in_(part_ids)).all()}
        if len(parts) != len(part_ids):
            raise ValueError("إحدى قطع الغيار غير موجودة")

    obj = SparePartRequest(
        request_number=data.request_number,
        request_date=data.request_date,
        source_type=data.source_type,
        fault_id=data.source_id if data.source_type == "fault" else None,
        repair_id=data.source_id if data.source_type == "repair" else None,
        equipment_id=equipment_id,
        status="pending",
        requested_by_id=user_id,
        notes=data.notes,
    )
    db.add(obj)
    db.flush()
    for item in data.items:
        values = item.model_dump(exclude={"spare_part_name"})
        obj.items.append(SparePartRequestItem(**values))
    db.commit()
    return get_request(db, obj.id)


def update_request(db: Session, obj: SparePartRequest, data: SparePartRequestUpdate):
    if obj.status != "pending":
        raise ValueError("لا يمكن تعديل طلب إلا وهو قيد الانتظار")
    values = data.model_dump(exclude_unset=True)
    if "request_number" in values:
        other = db.query(SparePartRequest).filter(
            SparePartRequest.request_number == values["request_number"],
            SparePartRequest.id != obj.id,
        ).first()
        if other:
            raise ValueError("رقم وثيقة الطلب مستخدم مسبقًا")
    if "request_date" in values:
        _, _, source_date = _source(db, obj.source_type, obj.fault_id or obj.repair_id)
        if values["request_date"] != source_date:
            raise ValueError("تاريخ الطلب يجب أن يطابق تاريخ المصدر")
    for key, value in values.items():
        setattr(obj, key, value)
    db.commit()
    return get_request(db, obj.id)


def delete_request(db: Session, obj: SparePartRequest):
    if obj.status == "approved":
        raise ValueError("لا يمكن حذف طلب معتمد")
    if any(item.received_quantity > 0 for item in obj.items):
        raise ValueError("لا يمكن حذف طلب يحتوي على كمية مستلمة")
    db.delete(obj)
    db.commit()


def add_item(db: Session, request_id: int, data: SparePartRequestItemCreate):
    request = get_request(db, request_id)
    if not request:
        raise ValueError("طلب الغيار غير موجود")
    if request.status not in {"pending", "approved"}:
        raise ValueError("لا يمكن إضافة بند إلا لطلب قيد الانتظار أو معتمد")
    if data.spare_part_name:
        part = db.query(SparePart).filter(SparePart.name == data.spare_part_name.strip()).first()
        if not part:
            raise ValueError("قطعة الغيار غير موجودة في سجل قطع الغيار")
        data.spare_part_id = part.id
    if db.query(SparePartRequestItem).filter_by(request_id=request_id, spare_part_id=data.spare_part_id).first():
        raise ValueError("قطعة الغيار موجودة بالفعل في الطلب")
    if not db.query(SparePart).filter(SparePart.id == data.spare_part_id).first():
        raise ValueError("قطعة الغيار غير موجودة")
    if data.received_quantity > 0 and (not data.received_date or not data.recipient or not data.supplier_institution):
        raise ValueError("عند تسجيل استلام يجب إدخال تاريخ الاستلام والمستلم والمؤسسة الممونة")
    item = SparePartRequestItem(request_id=request_id, **data.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def update_item(db: Session, item: SparePartRequestItem, data: SparePartRequestItemUpdate):
    if item.request.status == "cancelled":
        raise ValueError("لا يمكن تعديل طلب ملغى")
    values = data.model_dump(exclude_unset=True)
    if any(k in values for k in ("spare_part_id", "requested_quantity")) and item.request.status != "pending":
        raise ValueError("لا يمكن تعديل التعيين أو الكمية المطلوبة إلا لطلب قيد الانتظار")
    if item.received_quantity > 0 and any(k in values for k in ("spare_part_id", "requested_quantity")):
        raise ValueError("لا يمكن تعديل التعيين أو الكمية المطلوبة بعد تسجيل الاستلام")
    if values.get("spare_part_name"):
        part = db.query(SparePart).filter(SparePart.name == values["spare_part_name"].strip()).first()
        if not part:
            raise ValueError("قطعة الغيار غير موجودة في سجل قطع الغيار")
        values["spare_part_id"] = part.id
        values.pop("spare_part_name", None)
    if "spare_part_id" in values:
        duplicate = db.query(SparePartRequestItem).filter(
            SparePartRequestItem.request_id == item.request_id,
            SparePartRequestItem.spare_part_id == values["spare_part_id"],
            SparePartRequestItem.id != item.id,
        ).first()
        if duplicate:
            raise ValueError("قطعة الغيار موجودة بالفعل في الطلب")
        if not db.query(SparePart).filter(SparePart.id == values["spare_part_id"]).first():
            raise ValueError("قطعة الغيار غير موجودة")
    for key, value in values.items():
        setattr(item, key, value)
    if item.received_quantity > 0 and (not item.received_date or not item.recipient or not item.supplier_institution):
        raise ValueError("عند تسجيل استلام يجب إدخال تاريخ الاستلام والمستلم والمؤسسة الممونة")
    db.commit()
    db.refresh(item)
    return item


def delete_item(db: Session, item: SparePartRequestItem):
    if item.received_quantity > 0:
        raise ValueError("لا يمكن حذف بند تم تسجيل استلام له")
    if item.request.status != "pending":
        raise ValueError("لا يمكن حذف بند إلا من طلب قيد الانتظار")
    db.delete(item)
    db.commit()


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
    rows = db.query(SparePartRequestItem).join(SparePartRequest).options(
        joinedload(SparePartRequestItem.spare_part),
        joinedload(SparePartRequestItem.request).joinedload(SparePartRequest.equipment),
        joinedload(SparePartRequestItem.request).joinedload(SparePartRequest.fault),
        joinedload(SparePartRequestItem.request).joinedload(SparePartRequest.repair).joinedload(Repair.fault),
    ).filter(SparePartRequestItem.received_quantity > 0).order_by(
        SparePartRequest.request_date.desc(), SparePartRequest.id.desc(), SparePartRequestItem.id
    ).all()

    result = []
    for item in rows:
        req = item.request
        result.append({
            "request_number": req.request_number,
            "part_name": item.spare_part.name if item.spare_part else "—",
            "requested_quantity": item.requested_quantity,
            "received_quantity": item.received_quantity,
            "received_date": item.received_date,
            "equipment": {
                "asset_code": req.equipment.asset_code if req.equipment else "—",
            },
            "registration_number": req.equipment.registration_number if req.equipment else "—",
            "recipient": item.recipient or "—",
            "supplier_institution": item.supplier_institution or "—",
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
