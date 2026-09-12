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
from app.modules.batteries import services as battery_services
from app.modules.equipment import services as equipment_services
from app.modules.tires import services as tire_services
from app.modules.users.models import User

router = APIRouter()
templates = get_module_templates("app/modules/dashboard/templates")


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    status_counts = equipment_services.count_by_operational_status(db)
    total_equipment = sum(status_counts.values())
    broken_count = equipment_services.count_broken(db)

    # Dashboard display uses the current state only. Historical validation is
    # handled by the tire and battery services at the operation date.
    expired_tires = []
    for tire in tire_services.list_tires(db):
        state = tire_services.current_state(db, tire.id)
        if state and state.get("installed") and tire_services.tire_condition(tire, state) == "expired":
            equipment = state.get("equipment")
            position = state.get("position")
            expired_tires.append(
                {
                    "tire": tire,
                    "equipment": equipment,
                    "position": position,
                }
            )
    expired_tires.sort(
        key=lambda item: (
            item["equipment"].registration_number if item["equipment"] else "",
            item["position"].sort_order if item["position"] else 9999,
            item["tire"].serial_number,
        )
    )

    expired_batteries = []
    for battery in battery_services.list_batteries(db):
        state = battery_services.current_state(db, battery.id)
        if state and state.get("installed") and battery_services.status(battery, state) == "expired":
            expired_batteries.append(
                {
                    "battery": battery,
                    "equipment": state.get("equipment"),
                }
            )
    expired_batteries.sort(
        key=lambda item: (
            item["equipment"].registration_number if item["equipment"] else "",
            item["battery"].serial_number,
        )
    )

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": current_user,
            "total_equipment": total_equipment,
            "status_counts": status_counts,
            "broken_count": broken_count,
            "expired_tires": expired_tires,
            "expired_batteries": expired_batteries,
        },
    )
