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


@router.post("/document-import/preview", response_class=HTMLResponse)
async def preview_html(
    request: Request,
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
        return templates.TemplateResponse(
            request=request,
            name="upload.html",
            context={"request": request, "model_id": model_id, "user": current_user, "candidates": cands},
        )
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


@router.post("/document-import/preview/json", response_model=ImportPreviewResponse)
async def preview_json(
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
async def apply(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(Role.ADMIN, Role.FLEET_MANAGER)),
):
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            data = await request.json()
        except Exception:
            raise HTTPException(status_code=422, detail="JSON غير صالح")
        req = ImportApplyRequest(**data)
    else:
        form = await request.form()
        model_id_str = form.get("model_id")
        if not model_id_str:
            raise HTTPException(status_code=422, detail="model_id مفقود")
        try:
            model_id = int(model_id_str)
        except Exception:
            raise HTTPException(status_code=422, detail="model_id غير صالح")
        candidates_list = []
        idx = 0
        while True:
            def f(n):
                return form.get(f"candidates-{idx}-{n}")
            def fb(n):
                v = f(n)
                return v == "true" or v == "on" or v == "1"
            nmv = f("name_found")
            valf = f("value")
            defidv = f("definition_id")
            # detect end
            if nmv is None and valf is None and defidv is None:
                has_next = any(k.startswith(f"candidates-{idx+1}-") for k in form.keys())
                if not has_next:
                    break
            try:
                definition_id = int(defidv) if defidv not in (None, "", "None") else None
            except Exception:
                definition_id = None
            is_new = (f("is_new") or "false").lower() == "true"
            # edited detection using original values
            val_orig = f("value_original") or ""
            unit_orig = f("unit_original") or ""
            val = valf or ""
            unit = f("unit") or None
            edited = (val != val_orig) or (unit != unit_orig)
            candidates_list.append({
                "definition_id": definition_id,
                "name_found": nmv or None,
                "value": val,
                "unit": unit,
                "is_new": is_new,
                "approved": fb("approved"),
                "ignored": fb("ignored"),
                "edited": edited,
                "value_edited": val if edited else None,
                "unit_edited": unit if edited else None,
                "source_ref": f("source_ref") or None,
                "page": None,
                "sheet": f("sheet") or None,
                "cell": f("cell") or None,
                "confidence": 0.0,
            })
            idx += 1
            if idx > 5000:
                break
        req = ImportApplyRequest(model_id=model_id, candidates=candidates_list)
    res = apply_candidates(model_id=req.model_id, candidates=req.candidates, db=db, user_id=current_user.id if current_user else None)
    return res
