from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from app.core.dependencies import get_current_user
from app.core.templating import get_module_templates
from app.modules.users.models import User

router = APIRouter()
templates = get_module_templates("app/modules/spare_parts_movements/templates")

@router.get("/spare-parts-distribution", response_class=HTMLResponse)
def distribution_page(request: Request, user: User = Depends(get_current_user)):
    return templates.TemplateResponse(request=request, name="distribution.html", context={"request": request, "user": user})


@router.get("/spare-parts-return", response_class=HTMLResponse)
def return_page(request: Request, user: User = Depends(get_current_user)):
    return templates.TemplateResponse(request=request, name="return.html", context={"request": request, "user": user})


@router.get("/spare-parts-history/{request_item_id}", response_class=HTMLResponse)
def history_page(request: Request, request_item_id: int, user: User = Depends(get_current_user)):
    return templates.TemplateResponse(request=request, name="history.html", context={"request": request, "user": user, "request_item_id": request_item_id})
