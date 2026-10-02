from datetime import date

from sqlalchemy.orm import Session, joinedload

from app.modules.batteries.models import Battery
from app.modules.equipment.models import Equipment
from app.modules.maintenance.models import MaintenanceRecord
from app.modules.faults_repairs.models import Repair, SparePart
from app.modules.tires.models import Tire
from .models import SparePartRequest, SparePartRequestItem
from .schemas import SparePartRequestCreate, SparePartRequestItemUpdate, SparePartRequestStatusUpdate


SOURCE_MODELS = {
    "maintenance": (MaintenanceRecord, "maintenance_record_id"),
    "repair": (Repair, "repair_id"),
    "tire": (Tire, "tire_id"),
    "battery": (Battery, "battery_id"),
}


def _next_request_number(db: Session) -> str:
    last = db.query(SparePartRequest).order_by(SparePartRequest.id.desc()).first()
    return f"PR-{(last.id + 1 if last else 1):06d}"


def _source_equipment_id(source_type: str, source) -> int | None:
    if source_type == "maintenance":
        return source.equipment_id
    if source_type == "repair":
        return source.fault.equipment_id if source.fault else None
    return None


def create_request(db: Session, data: SparePartRequestCreate, user_id: int | None = None):
    if data.source_type not in SOURCE_MODELS:
        raise ValueError("مصدر طلب قطع الغيار غير صالح")
    if data.priority not in {"normal", "urgent"}:
        raise ValueError("أولوية الطلب غير صالحة")
    if data.needed_by_date and data.needed_by_date < data.request_date:
        raise ValueError("تاريخ الحاجة لا يمكن أن يسبق تاريخ الطلب")

    model, fk_name = SOURCE_MODELS[data.source_type]
    source = db.query(model).filter(model.id == data.source_id).first()
    if not source:
        raise ValueError("المصدر المحدد لطلب قطع الغيار غير موجود")

    part_ids = [item.spare_part_id for item in data.items]
    if len(part_ids) != len(set(part_ids)):
        raise ValueError("لا يمكن تكرار قطعة الغيار داخل الطلب")
    parts = {p.id: p for p in db.query(SparePart).filter(SparePart.id.in_(part_ids)).all()}
    if len(parts) != len(part_ids):
        raise ValueError("إحدى قطع الغيار المحددة غير موجودة")

    equipment_id = data.equipment_id
    source_equipment_id = _source_equipment_id(data.source_type, source)
    if source_equipment_id is not None:
        if equipment_id is not None and equipment_id != source_equipment_id:
            raise ValueError("العتاد لا يطابق مصدر الطلب")
        equipment_id = source_equipment_id

    kwargs = {
        "request_number": _next_request_number(db),
        "request_date": data.request_date,
        "needed_by_date": data.needed_by_date,
        "source_type": data.source_type,
        fk_name: data.source_id,
        "equipment_id": equipment_id,
        "priority": data.priority,
        "status": "pending",
        "requested_by_id": user_id,
        "notes": data.notes,
    }
    obj = SparePartRequest(**kwargs)
    db.add(obj)
    db.flush()
    for item in data.items:
        obj.items.append(SparePartRequestItem(
            spare_part_id=item.spare_part_id,
            requested_quantity=item.requested_quantity,
            notes=item.notes,
        ))
    db.commit()
    db.refresh(obj)
    return obj


def list_requests(db: Session, status: str | None = None, source_type: str | None = None):
    q = db.query(SparePartRequest).options(
        joinedload(SparePartRequest.items).joinedload(SparePartRequestItem.spare_part)
    )
    if status:
        q = q.filter(SparePartRequest.status == status)
    if source_type:
        q = q.filter(SparePartRequest.source_type == source_type)
    return q.order_by(SparePartRequest.request_date.desc(), SparePartRequest.id.desc()).all()


def get_request(db: Session, request_id: int):
    return db.query(SparePartRequest).options(
        joinedload(SparePartRequest.items).joinedload(SparePartRequestItem.spare_part)
    ).filter(SparePartRequest.id == request_id).first()


def update_status(db: Session, obj: SparePartRequest, data: SparePartRequestStatusUpdate):
    if data.status not in REQUEST_STATUSES:
        raise ValueError("حالة طلب قطع الغيار غير صالحة")
    if data.status == "fulfilled":
        for item in obj.items:
            if item.issued_quantity < item.approved_quantity or item.approved_quantity < item.requested_quantity:
                raise ValueError("لا يمكن إغلاق الطلب كمكتمل قبل اعتماد وتسليم الكميات المطلوبة")
    obj.status = data.status
    db.commit()
    db.refresh(obj)
    return obj


def update_item(db: Session, item: SparePartRequestItem, data: SparePartRequestItemUpdate):
    if data.approved_quantity > item.requested_quantity:
        raise ValueError("الكمية المعتمدة تتجاوز الكمية المطلوبة")
    if data.issued_quantity > data.approved_quantity:
        raise ValueError("الكمية المسلّمة تتجاوز الكمية المعتمدة")
    item.approved_quantity = data.approved_quantity
    item.issued_quantity = data.issued_quantity

    request = item.request
    if all(i.issued_quantity == i.requested_quantity for i in request.items):
        request.status = "fulfilled"
    elif any(i.issued_quantity > 0 for i in request.items):
        request.status = "partially_fulfilled"
    elif any(i.approved_quantity > 0 for i in request.items):
        request.status = "approved"
    db.commit()
    db.refresh(item)
    return item


def pending_count(db: Session) -> int:
    return db.query(SparePartRequest).filter(
        SparePartRequest.status.in_({"pending", "approved", "partially_fulfilled"})
    ).count()
