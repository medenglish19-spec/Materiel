from fastapi import APIRouter,Depends,File,Form,HTTPException,UploadFile
from sqlalchemy.orm import Session
from app.core.permissions import Role,require_role
from app.database.session import get_db
from app.modules.users.models import User
from .schemas import ImportPreviewResponse,ImportApplyRequest,ImportApplyResponse
from .services import preview_from_document,apply_candidates
router=APIRouter(prefix="/document-import",tags=["document-import"])
MAX_BYTES=15*1024*1024
@router.post("/preview",response_model=ImportPreviewResponse)
async def preview_document(model_id:int=Form(...),mode:str=Form("extract"),requested:str=Form(""),file:UploadFile=File(...),db:Session=Depends(get_db),_user:User=Depends(require_role(Role.ADMIN))):
 content=await file.read(MAX_BYTES+1)
 if len(content)>MAX_BYTES:raise HTTPException(413,"حجم الملف يتجاوز 15 ميغابايت")
 try:
  candidates,warnings=preview_from_document(db,model_id,file.filename or "",content,mode,[x.strip() for x in requested.split(",") if x.strip()])
 except ValueError as e:raise HTTPException(400,str(e)) from e
 return ImportPreviewResponse(candidates=candidates,warnings=warnings,filename=file.filename or "",model_id=model_id)
@router.post("/apply",response_model=ImportApplyResponse)
def apply_document(payload:ImportApplyRequest,db:Session=Depends(get_db),_user:User=Depends(require_role(Role.ADMIN))):
 try:applied,skipped=apply_candidates(db,payload.model_id,payload.candidates)
 except ValueError as e:raise HTTPException(400,str(e)) from e
 except Exception as e:raise HTTPException(500,"تعذر حفظ الخصائص؛ تم التراجع عن العملية كاملة") from e
 return ImportApplyResponse(applied=applied,skipped=skipped,message=f"تم حفظ {applied} خاصية معتمدة.")
