from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from app.core.dependencies import get_current_user
from app.core.templating import get_module_templates
from app.modules.users.models import User

router = APIRouter()
templates = get_module_templates("app/modules/maintenance/templates")


def render_page(template_name: str, request: Request, current_user: User):
    return templates.TemplateResponse(
        template_name,
        {"request": request, "user": current_user},
    )


@router.get("/maintenance", response_class=HTMLResponse)
@router.get("/maintenance/periodic", response_class=HTMLResponse)
def periodic_maintenance_page(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    return render_page("maintenance_dashboard.html", request, current_user)


@router.get("/maintenance/rules", response_class=HTMLResponse)
def maintenance_rules_page(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    return render_page("maintenance_rules.html", request, current_user)


@router.get("/maintenance/records", response_class=HTMLResponse)
def maintenance_records_page(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    return render_page("maintenance_records.html", request, current_user)


@router.get("/maintenance/due", response_class=HTMLResponse)
def maintenance_due_page(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    return render_page("maintenance_due.html", request, current_user)
