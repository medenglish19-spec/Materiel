"""
modules/dashboard/router.py
------------------------------
لوحة التحكم تجمع مؤشرات الوحدات من خدماتها، مع إبقاء منطق البيانات داخل
الوحدات المالكة لها.
"""

from datetime import date

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.templating import get_module_templates
from app.database.session import get_db
from app.modules.batteries import services as battery_services
from app.modules.equipment import services as equipment_services
from app.modules.tires import batch_state as tire_batch_state
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

    # Dashboard display uses current state only. Batch loaders avoid an N+1
    # movement query per asset while preserving the existing state shape.
    tires, tire_states = tire_batch_state.current_states(db)
    expired_tires = []
    for tire in tires:
        state = tire_states.get(tire.id)
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

    batteries, battery_states = battery_services.current_states(db)
    validity_years = battery_services.get_validity_years(db)
    today = date.today()
    expired_batteries = []
    for battery in batteries:
        state = battery_states.get(battery.id)
        if not state or not state.get("installed"):
            continue
        equipment = state.get("equipment")
        due_date = battery_services.replacement_due_date(db, battery, equipment)
        # replacement_due_date() normally performs a settings lookup. The
        # dashboard has already loaded the single system rule above, so derive
        # the same date here to avoid a query for every battery.
        first_service = getattr(equipment, "first_service_date", None) if equipment else None
        if first_service:
            due_date = battery_services._add_years(first_service, validity_years)
        else:
            base = battery.manufacture_date or battery.receipt_date
            due_date = battery_services._add_years(base, validity_years) if base else None
        if due_date and today >= due_date:
            expired_batteries.append(
                {
                    "battery": battery,
                    "equipment": equipment,
                    "due_date": due_date,
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
