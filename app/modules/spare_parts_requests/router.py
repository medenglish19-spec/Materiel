from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database.session import get_db
from app.modules.users.models import User
from . import services
from .models import SparePartRequestItem
from .models import SparePartRequest
from app.modules.spare_parts_movements.models import SparePartMovementDocument, SparePartMovementItem
from app.modules.spare_parts_movements import services as movement_services
from .schemas import (
    SparePartRequestCreate,
    SparePartRequestItemCreate,
    SparePartRequestItemUpdate,
    SparePartRequestOut,
    SparePartRequestStatusUpdate,
    SparePartRequestItemOut,
    SparePartRequestUpdate,
)

router = APIRouter(prefix="/api/spare-parts-requests")


@router.get("", response_model=list[SparePartRequestOut])
def requests(status: str | None = None, source_type: str | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return services.list_requests(db, status, source_type)


@router.post("", response_model=SparePartRequestOut, status_code=201)
def create(data: SparePartRequestCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        return services.serialize_request(services.create_request(db, data, user.id))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/sources/{source_type}")
def sources(source_type: str, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    if source_type not in {"fault", "repair"}:
        raise HTTPException(400, "مصدر غير صالح")
    return services.source_options(db, source_type)


@router.get("/received-register")
def received(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return services.received_register(db)


@router.get("/stats/pending-count")
def pending(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return {"count": services.pending_count(db)}


@router.get("/{request_id:int}", response_model=SparePartRequestOut)
def get(request_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    obj = services.get_request(db, request_id)
    if not obj:
        raise HTTPException(404, "طلب الغيار غير موجود")
    return services.serialize_request(obj)


@router.patch("/{request_id:int}", response_model=SparePartRequestOut)
def update(request_id: int, data: SparePartRequestUpdate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    obj = services.get_request(db, request_id)
    if not obj:
        raise HTTPException(404, "طلب الغيار غير موجود")
    try:
        return services.serialize_request(services.update_request(db, obj, data))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.delete("/{request_id:int}")
def delete(request_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    obj = services.get_request(db, request_id)
    if not obj:
        raise HTTPException(404, "طلب الغيار غير موجود")
    try:
        movement_result = services.delete_request(db, obj)
        return {"ok": True, **movement_result}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/{request_id}/delete-impact")
def delete_impact(request_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    obj = services.get_request(db, request_id)
    if not obj:
        raise HTTPException(404, "طلب الغيار غير موجود")
    item_ids = {item.id for item in obj.items}
    plan = movement_services.request_item_movement_deletion_plan(db, item_ids)
    deleted_lines = len(plan["lines"])
    deleted_documents = len(plan["documents_to_delete"])
    affected_docs = [doc.document_number for doc in plan["documents"]]
    return {
        "label": obj.request_number,
        "effects": [
            {"label": "بنود الطلب التي ستحذف", "count": len(obj.items)},
            {"label": "سطور حركات الغيار التي ستحذف", "count": deleted_lines},
            {"label": "وثائق الحركة التي ستحذف بالكامل", "count": deleted_documents},
            {"label": "وثائق الحركة التي ستبقى مع تعديل بنودها", "count": len(plan["documents"]) - deleted_documents, "kind": "remain"},
            {"label": "ارتباطات العطل/الإصلاح/العتاد التي ستنفصل عن الطلب", "count": sum(bool(value) for value in (obj.fault_id, obj.repair_id, obj.equipment_id)), "kind": "unlink"},
        ],
        "documents": affected_docs,
    }


@router.patch("/{request_id}/status", response_model=SparePartRequestOut)
def status(request_id: int, data: SparePartRequestStatusUpdate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    obj = services.get_request(db, request_id)
    if not obj:
        raise HTTPException(404, "طلب الغيار غير موجود")
    try:
        return services.update_status(db, obj, data)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.post("/{request_id}/items", response_model=SparePartRequestItemOut, status_code=201)
def add_item(request_id: int, data: SparePartRequestItemCreate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    try:
        return services.add_item(db, request_id, data)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/items/{item_id}", response_model=SparePartRequestItemOut)
def get_item(item_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    obj = db.query(SparePartRequestItem).filter(SparePartRequestItem.id == item_id).first()
    if not obj:
        raise HTTPException(404, "بند طلب الغيار غير موجود")
    return services.serialize_item(obj)


@router.patch("/items/{item_id}", response_model=SparePartRequestItemOut)
def item(item_id: int, data: SparePartRequestItemUpdate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    obj = db.query(SparePartRequestItem).filter(SparePartRequestItem.id == item_id).first()
    if not obj:
        raise HTTPException(404, "بند طلب الغيار غير موجود")
    try:
        return services.update_item(db, obj, data)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.delete("/items/{item_id}/receipt")
def undo_receipt(item_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    obj = db.query(SparePartRequestItem).filter(SparePartRequestItem.id == item_id).first()
    if not obj:
        raise HTTPException(404, "بند طلب الغيار غير موجود")
    try:
        return services.serialize_item(services.undo_item_receipt(db, obj))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/items/{item_id}/receipt-impact")
def receipt_impact(item_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    obj = db.query(SparePartRequestItem).filter(SparePartRequestItem.id == item_id).first()
    if not obj:
        raise HTTPException(404, "بند طلب الغيار غير موجود")
    request = obj.request
    receipt_items = [row for row in request.items if row.received_quantity > 0 or row.supplier_institution]
    ids = [row.id for row in request.items]
    movement_count = db.query(SparePartMovementItem.id).filter(or_(
        SparePartMovementItem.request_item_id.in_(ids), SparePartMovementItem.received_request_item_id.in_(ids)
    )).count() if ids else 0
    blocked = None
    if not receipt_items:
        blocked = "لا يوجد استلام مسجل لهذا الطلب."
    return {"label": request.request_number, "effects": [
        {"label": "بنود الطلب التي سيعاد استلامها إلى حالة قيد الانتظار", "count": len(receipt_items)},
        {"label": "إجمالي الكمية المستلمة التي ستعاد إلى غير مستلمة", "count": sum((row.received_quantity or 0) for row in receipt_items)},
        {"label": "تاريخ وبيانات جهة الاستلام التي ستزال", "count": 1},
        {"label": "سطور حركات التوزيع والإرجاع التابعة التي ستحذف", "count": movement_count},
    ], "blocked": blocked}


@router.delete("/items/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    obj = db.query(SparePartRequestItem).filter(SparePartRequestItem.id == item_id).first()
    if not obj:
        raise HTTPException(404, "بند طلب الغيار غير موجود")
    try:
        services.delete_item(db, obj)
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/items/{item_id}/delete-impact")
def delete_item_impact(item_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    obj = db.query(SparePartRequestItem).filter(SparePartRequestItem.id == item_id).first()
    if not obj:
        raise HTTPException(404, "بند طلب الغيار غير موجود")
    distributions = db.query(SparePartMovementItem).join(SparePartMovementDocument).filter(
        SparePartMovementDocument.document_type == "distribution",
        or_(SparePartMovementItem.request_item_id == obj.id, SparePartMovementItem.received_request_item_id == obj.id),
    ).all()
    distribution_ids = [line.id for line in distributions]
    movement_lines = db.query(SparePartMovementItem).join(SparePartMovementDocument).filter(or_(
        SparePartMovementItem.request_item_id == obj.id, SparePartMovementItem.received_request_item_id == obj.id
    )).all()
    return_lines = db.query(SparePartMovementItem).join(SparePartMovementDocument).filter(
        SparePartMovementDocument.document_type == "return",
        or_(
            SparePartMovementItem.request_item_id == obj.id,
            SparePartMovementItem.received_request_item_id == obj.id,
            SparePartMovementItem.source_item_id.in_(distribution_ids) if distribution_ids else False,
        ),
    ).all()
    fully_removed_distribution_docs = [
        document_id for document_id in {line.document_id for line in distributions}
        if db.query(SparePartMovementItem.id).filter(SparePartMovementItem.document_id == document_id).count()
        == sum(line.document_id == document_id for line in distributions)
    ]
    if fully_removed_distribution_docs:
        legacy_return_doc_ids = [row[0] for row in db.query(SparePartMovementDocument.id).filter(
            SparePartMovementDocument.document_type == "return",
            SparePartMovementDocument.source_document_id.in_(fully_removed_distribution_docs),
        ).all()]
        if legacy_return_doc_ids:
            legacy_lines = db.query(SparePartMovementItem).filter(
                SparePartMovementItem.document_id.in_(legacy_return_doc_ids)
            ).all()
            return_lines.extend(line for line in legacy_lines if line.id not in {x.id for x in return_lines})
    affected = movement_lines + [line for line in return_lines if line.id not in {x.id for x in movement_lines}]
    doc_ids = {line.document_id for line in affected}
    docs = db.query(SparePartMovementDocument).filter(SparePartMovementDocument.id.in_(doc_ids)).all() if doc_ids else []
    lines_per_doc = {}
    for line in affected:
        lines_per_doc[line.document_id] = lines_per_doc.get(line.document_id, 0) + 1
    deleted_docs = sum(lines_per_doc.get(doc.id, 0) == len(doc.items) for doc in docs)
    return {"label": obj.part_name or f"بند #{obj.id}", "effects": [
        {"label": "البند الذي سيحذف من الطلب", "count": 1},
        {"label": "الكمية المطلوبة التي ستزال", "count": obj.requested_quantity},
        {"label": "سطور التوزيع والإرجاع التابعة التي ستحذف", "count": len(affected)},
        {"label": "وثائق الحركة التي ستحذف بالكامل", "count": deleted_docs},
        {"label": "وثائق الحركة المشتركة التي ستبقى ببنودها الأخرى", "count": len(doc_ids) - deleted_docs, "kind": "remain"},
    ], "blocked": None}
