"""
modules/dashboard/router.py
------------------------------
لوحة التحكم تجمع مؤشرات الوحدات من خدماتها، مع إبقاء منطق البيانات داخل
الوحدات المالكة لها.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.templating import get_module_templates
from app.database.session import get_db
from app.modules.faults_repairs import services as faults_repairs_services
from app.modules.equipment import services as equipment_services
from app.modules.notifications.services import get_all_notifications
from app.modules.spare_parts_requests import services as spare_parts_request_services
from app.modules.users.models import User

router = APIRouter()
templates = get_module_templates("app/modules/dashboard/templates")


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    equipment = equipment_services.list_equipment(db, limit=100000)
    effective_statuses = equipment_services.effective_operational_statuses(db, equipment)
    status_counts = {}
    for status in effective_statuses.values():
        status_counts[status] = status_counts.get(status, 0) + 1
    active_repairs = equipment_services.active_repair_workshops(
        db, [item.id for item in equipment]
    )
    internal_repair_count = sum(
        workshop == "in_maintenance" for workshop in active_repairs.values()
    )
    external_repair_count = sum(
        workshop == "in_external_workshop" for workshop in active_repairs.values()
    )
    total_equipment = len(equipment)
    technically_ready_count = sum(1 for item in equipment if item.technical_condition == "ready")
    broken_count = sum(1 for item in equipment if item.technical_condition == "broken")
    readiness_percentage = (technically_ready_count / total_equipment * 100) if total_equipment else 0
    waiting_parts_count = spare_parts_request_services.pending_count(db)

    # الإشعارات الموحّدة: كل مزوّد يسجّل تنبيهات وحدته، والموحّد يدمجها بالخطورة.
    notifications = get_all_notifications(db)

    return templates.TemplateResponse(
        request=request, name="dashboard.html", context={
            "request": request,
            "user": current_user,
            "total_equipment": total_equipment,
            "status_counts": status_counts,
            "internal_repair_count": internal_repair_count,
            "external_repair_count": external_repair_count,
            "broken_count": broken_count,
            "technically_ready_count": technically_ready_count,
            "readiness_percentage": readiness_percentage,
            "waiting_parts_count": waiting_parts_count,
            "notifications": notifications,
        },
    )
