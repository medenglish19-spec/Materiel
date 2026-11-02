from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.templating import get_module_templates
from app.database.session import get_db
from app.modules.faults_repairs.models import SparePart
from app.modules.users.models import User

router = APIRouter()
templates = get_module_templates("app/modules/spare_parts_requests/templates")


@router.get("/spare-parts", response_class=HTMLResponse)
def spare_parts_page(request: Request, user: User = Depends(get_current_user)):
    return templates.TemplateResponse(request=request, name="index.html", context={"request": request, "user": user})


@router.get("/spare-parts-requests", response_class=HTMLResponse)
def requests_page(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    parts = db.query(SparePart).order_by(SparePart.name).all()
    return templates.TemplateResponse(
        request=request,
        name="requests.html",
        context={"request": request, "user": user, "parts": parts},
    )


@router.get("/spare-parts-received", response_class=HTMLResponse)
def received_page(request: Request, user: User = Depends(get_current_user)):
    return templates.TemplateResponse(
        request=request,
        name="received.html",
        context={"request": request, "user": user},
    )
