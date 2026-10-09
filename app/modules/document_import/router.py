from __future__ import annotations
import os
import tempfile
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.permissions import Role, require_role
from app.core.templating import get_module_templates
from app.database.session import get_db
from app.modules.users.models import User

from .schemas import ImportPreviewResponse, ImportApplyRequest
from .services import preview_from_document, apply_candidates

router = APIRouter()
templates = get_module_templates("app/modules/document_import/templates")

ALLOWED = {".pdf", ".docx", ".xlsx", ".xls"}


@router.get("/document-import/upload", response_class=HTMLResponse)
def upload_page(
    request: Request,
    model_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(Role.ADMIN, Role.FLEET_MANAGER)),
):
    return templates.TemplateResponse(request=request, name="upload.html", context={"request": request, "model_id": model_id, "user": current_user})


@router.post("/document-import/preview", response_model=ImportPreviewResponse)
async def preview(
    model_id: int = Form(...),
    mode: str = Form("extract"),
    requested: List[str] = Form([]),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(Role.ADMIN, Role.FLEET_MANAGER)),
):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED:
        raise HTTPException(status_code=400, detail="نوع الملف غير مدعوم. المدعوم: PDF, DOCX, XLSX")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    try:
        data = await file.read()
        tmp.write(data)
        tmp.close()
        cands = preview_from_document(model_id=model_id, file_path=tmp.name, mode=mode, requested=requested or [], db=db)
        return ImportPreviewResponse(candidates=cands)
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


@router.post("/document-import/apply")
def apply(
    req: ImportApplyRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(Role.ADMIN, Role.FLEET_MANAGER)),
):
    res = apply_candidates(model_id=req.model_id, candidates=req.candidates, db=db, user_id=current_user.id if current_user else None)
    return res
