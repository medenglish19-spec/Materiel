from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database.session import get_db
from app.modules.users.models import User
from . import services
from .models import SparePartRequestItem
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


@router.get("/{request_id}", response_model=SparePartRequestOut)
def get(request_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    obj = services.get_request(db, request_id)
    if not obj:
        raise HTTPException(404, "طلب الغيار غير موجود")
    return services.serialize_request(obj)


@router.patch("/{request_id}", response_model=SparePartRequestOut)
def update(request_id: int, data: SparePartRequestUpdate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    obj = services.get_request(db, request_id)
    if not obj:
        raise HTTPException(404, "طلب الغيار غير موجود")
    try:
        return services.serialize_request(services.update_request(db, obj, data))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.delete("/{request_id}")
def delete(request_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    obj = services.get_request(db, request_id)
    if not obj:
        raise HTTPException(404, "طلب الغيار غير موجود")
    try:
        services.delete_request(db, obj)
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(400, str(exc))


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


@router.patch("/items/{item_id}", response_model=SparePartRequestItemOut)
def item(item_id: int, data: SparePartRequestItemUpdate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    obj = db.query(SparePartRequestItem).filter(SparePartRequestItem.id == item_id).first()
    if not obj:
        raise HTTPException(404, "بند طلب الغيار غير موجود")
    try:
        return services.update_item(db, obj, data)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


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


@router.get("/stats/pending-count")
def pending(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return {"count": services.pending_count(db)}
