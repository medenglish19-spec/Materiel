from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.database.session import get_db
from app.modules.users.models import User
from . import services
from .models import SparePartRequestItem
from .schemas import (
    SparePartRequestCreate, SparePartRequestItemOut, SparePartRequestItemUpdate,
    SparePartRequestOut, SparePartRequestStatusUpdate,
)

router = APIRouter(prefix="/api/spare-parts-requests")


@router.get("", response_model=list[SparePartRequestOut])
def requests(status: str | None = None, source_type: str | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return services.list_requests(db, status, source_type)


@router.post("", response_model=SparePartRequestOut, status_code=201)
def create(data: SparePartRequestCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        return services.create_request(db, data, user.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/stats/pending-count")
def pending(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return {"count": services.pending_count(db)}
@router.get("/{request_id}", response_model=SparePartRequestOut)
def get(request_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    obj = services.get_request(db, request_id)
    if not obj:
        raise HTTPException(404, "طلب قطع الغيار غير موجود")
    return obj


@router.patch("/{request_id}/status", response_model=SparePartRequestOut)
def status(request_id: int, data: SparePartRequestStatusUpdate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    obj = services.get_request(db, request_id)
    if not obj:
        raise HTTPException(404, "طلب قطع الغيار غير موجود")
    try:
        return services.update_status(db, obj, data)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/stats/pending-count")
def pending(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return {"count": services.pending_count(db)}
@router.patch("/items/{item_id}", response_model=SparePartRequestItemOut)
def item(item_id: int, data: SparePartRequestItemUpdate, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    obj = db.query(SparePartRequestItem).filter(SparePartRequestItem.id == item_id).first()
    if not obj:
        raise HTTPException(404, "بند طلب قطع الغيار غير موجود")
    try:
        return services.update_item(db, obj, data)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


