from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.modules.spare_parts_requests.models import SparePartRequest, SparePartRequestItem
from .models import SparePartMovementDocument, SparePartMovementItem
from .schemas import MovementDocumentCreate

DOCUMENT_NUMBER_TAKEN = "رقم وثيقة التوزيع أو الإرجاع مستخدم مسبقًا، يرجى إدخال رقم آخر."


def _number(value: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ValueError("رقم الوثيقة مطلوب")
    return value


def _movement_totals(db: Session, request_item_id: int):
    rows = db.query(SparePartMovementDocument.document_type, SparePartMovementItem.quantity).join(
        SparePartMovementItem, SparePartMovementItem.document_id == SparePartMovementDocument.id
    ).filter(SparePartMovementItem.request_item_id == request_item_id).all()
    distributed = sum((Decimal(str(q)) for typ, q in rows if typ == "distribution"), Decimal("0"))
    returned = sum((Decimal(str(q)) for typ, q in rows if typ == "return"), Decimal("0"))
    return distributed, returned


def available_quantity(db: Session, item: SparePartRequestItem) -> Decimal:
    distributed, returned = _movement_totals(db, item.id)
    received = Decimal(str(item.received_quantity or 0))
    available = received - distributed - returned
    return available if available > 0 else Decimal("0")


def _validate_item(db: Session, request_item_id: int, quantity: Decimal, movement_type: str):
    item = db.query(SparePartRequestItem).options(
        joinedload(SparePartRequestItem.request), joinedload(SparePartRequestItem.spare_part)
    ).filter(SparePartRequestItem.id == request_item_id).with_for_update().first()
    if not item:
        raise ValueError("بند الغيار المستلم غير موجود")
    if item.received_quantity <= 0:
        raise ValueError("لا يمكن التوزيع أو الإرجاع لغيار لم يُستلم")
    available = available_quantity(db, item)
    if quantity > available:
        label = "للتوزيع" if movement_type == "distribution" else "للإرجاع"
        raise ValueError(f"الكمية المتاحة {label} هي {available} فقط")
    return item


def create_document(db: Session, data: MovementDocumentCreate, user_id: int | None = None):
    number = _number(data.document_number)
    if db.query(SparePartMovementDocument.id).filter(SparePartMovementDocument.document_number == number).first():
        raise ValueError(DOCUMENT_NUMBER_TAKEN)
    ids = [line.request_item_id for line in data.items]
    if len(ids) != len(set(ids)):
        raise ValueError("لا يمكن تكرار نفس الغيار داخل الوثيقة")
    obj = SparePartMovementDocument(
        document_number=number, document_type=data.document_type, document_date=data.document_date,
        issuer=data.issuer, recipient=data.recipient, beneficiary=data.beneficiary.strip() if data.beneficiary else None,
        notes=data.notes.strip() if data.notes else None, created_by_id=user_id,
    )
    db.add(obj)
    try:
        db.flush()
        for line in data.items:
            item = _validate_item(db, line.request_item_id, line.quantity, data.document_type)
            obj.items.append(SparePartMovementItem(request_item_id=item.id, quantity=line.quantity, notes=line.notes.strip() if line.notes else None))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if "document_number" in str(getattr(exc, "orig", exc)):
            raise ValueError(DOCUMENT_NUMBER_TAKEN) from exc
        raise
    return get_document(db, obj.id)


def _serialize_item(item):
    ri = item.request_item
    return {"id": item.id, "request_item_id": item.request_item_id, "part_name": ri.part_name or (ri.spare_part.name if ri.spare_part else None), "request_number": ri.request.request_number if ri.request else None, "quantity": item.quantity, "notes": item.notes}


def serialize_document(doc):
    return {"id": doc.id, "document_number": doc.document_number, "document_type": doc.document_type, "document_date": doc.document_date, "issuer": doc.issuer, "recipient": doc.recipient, "beneficiary": doc.beneficiary, "notes": doc.notes, "items": [_serialize_item(x) for x in doc.items]}


def _options():
    return [
        joinedload(SparePartMovementDocument.items).joinedload(SparePartMovementItem.request_item).joinedload(SparePartRequestItem.spare_part),
        joinedload(SparePartMovementDocument.items).joinedload(SparePartMovementItem.request_item).joinedload(SparePartRequestItem.request),
    ]


def get_document(db: Session, document_id: int):
    return db.query(SparePartMovementDocument).options(*_options()).filter(SparePartMovementDocument.id == document_id).first()


def list_documents(db: Session, document_type: str | None = None):
    q = db.query(SparePartMovementDocument).options(*_options())
    if document_type:
        q = q.filter(SparePartMovementDocument.document_type == document_type)
    return [serialize_document(x) for x in q.order_by(SparePartMovementDocument.document_date.desc(), SparePartMovementDocument.id.desc()).all()]


def available_register(db: Session):
    items = db.query(SparePartRequestItem).join(SparePartRequest).options(
        joinedload(SparePartRequestItem.request), joinedload(SparePartRequestItem.spare_part),
        joinedload(SparePartRequestItem.request).joinedload(SparePartRequest.equipment),
    ).filter(SparePartRequestItem.received_quantity > 0).order_by(SparePartRequest.request_date.desc(), SparePartRequest.id.desc(), SparePartRequestItem.id).all()
    result = []
    for item in items:
        available = available_quantity(db, item)
        if available <= 0:
            continue
        result.append({
            "request_item_id": item.id, "request_number": item.request.request_number,
            "part_name": item.part_name or (item.spare_part.name if item.spare_part else "—"),
            "received_quantity": item.received_quantity, "available_quantity": available,
            "received_date": item.request.received_date or item.received_date,
            "recipient": item.recipient or "—",
            "equipment_code": item.request.equipment.asset_code if item.request.equipment else "—",
            "registration_number": item.request.equipment.registration_number if item.request.equipment else "—",
        })
    return result
