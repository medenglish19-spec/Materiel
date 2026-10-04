from fastapi import APIRouter, Depends, HTTPException
from app.core.dependencies import get_current_user
from app.database.session import get_db
from app.modules.users.models import User
from . import services
from .schemas import MovementDocumentCreate, MovementDocumentOut

router = APIRouter(prefix="/api/spare-parts-movements")

@router.get("", response_model=list[MovementDocumentOut])
def documents(document_type: str | None = None, db=Depends(get_db), _: User = Depends(get_current_user)):
    return services.list_documents(db, document_type)

@router.get("/available")
def available(db=Depends(get_db), _: User = Depends(get_current_user)):
    return services.available_register(db)

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
