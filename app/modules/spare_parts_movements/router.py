from fastapi import APIRouter, Depends, HTTPException
from app.core.dependencies import get_current_user
from app.database.session import get_db
from app.modules.users.models import User
from . import services
from .schemas import MovementDocumentCreate, MovementDocumentOut, MovementDocumentUpdate

router = APIRouter(prefix="/api/spare-parts-movements")

@router.get("", response_model=list[MovementDocumentOut])
def documents(document_type: str | None = None, db=Depends(get_db), _: User = Depends(get_current_user)):
    return services.list_documents(db, document_type)

@router.get("/returnable")
def returnable(exclude_document_id: int | None = None, db=Depends(get_db), _: User = Depends(get_current_user)):
    return services.return_register(db, exclude_document_id)


@router.get("/available")
def available(exclude_document_id: int | None = None, db=Depends(get_db), _: User = Depends(get_current_user)):
    return services.available_register(db, exclude_document_id)

@router.get("/history/{request_item_id}")
def item_history(request_item_id: int, db=Depends(get_db), _: User = Depends(get_current_user)):
    try:
        return services.history(db, request_item_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))


@router.get("/{document_id}", response_model=MovementDocumentOut)
def get(document_id: int, db=Depends(get_db), _: User = Depends(get_current_user)):
    obj = services.get_document(db, document_id)
    if not obj:
        raise HTTPException(404, "وثيقة الغيار غير موجودة")
    return services.serialize_document(obj)

@router.post("", response_model=MovementDocumentOut, status_code=201)
def create(data: MovementDocumentCreate, db=Depends(get_db), user: User = Depends(get_current_user)):
    try:
        return services.serialize_document(services.create_document(db, data, user.id))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.patch("/{document_id}", response_model=MovementDocumentOut)
def update(document_id: int, data: MovementDocumentUpdate, db=Depends(get_db), user: User = Depends(get_current_user)):
    try:
        return services.serialize_document(services.update_document(db, document_id, data, user.id))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.delete("/{document_id}")
def delete(document_id: int, db=Depends(get_db), _: User = Depends(get_current_user)):
    try:
        services.delete_document(db, document_id)
        return {"ok": True}
    except ValueError as exc:
        raise HTTPException(400, str(exc))
