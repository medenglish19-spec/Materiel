from datetime import date
from decimal import Decimal, InvalidOperation
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from app.core.dependencies import get_current_user
from app.core.templating import get_module_templates
from app.database.session import get_db
from app.modules.equipment.models import Equipment
from app.modules.missions import services
from app.modules.users.models import User

router = APIRouter()
templates = get_module_templates("app/modules/missions/templates")


def dec(value):
    if not value: return None
    try: return Decimal(value)
    except (InvalidOperation, ValueError): raise HTTPException(400, "قيمة العداد غير صالحة")


@router.get("/missions", response_class=HTMLResponse)
def missions_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    missions = [{"mission": m, "status": services.mission_status(m)} for m in services.list_missions(db)]
    return templates.TemplateResponse("missions.html", {"request": request, "user": current_user, "missions": missions, "equipment": db.query(Equipment).order_by(Equipment.registration_number, Equipment.id).all(), "counts": services.counts(db)})


@router.post("/missions")
def create_mission(equipment_id: int = Form(...), driver_name: str = Form(""), mission_document: str = Form(""), purpose: str = Form(""), destination: str = Form(""), start_date: date = Form(...), end_date: date | None = Form(None), departure_meter: str | None = Form(None), return_meter: str | None = Form(None), notes: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        services.add_mission(db, {"equipment_id": equipment_id, "driver_name": driver_name.strip() or None, "mission_document": mission_document.strip() or None, "purpose": purpose.strip() or None, "destination": destination.strip() or None, "start_date": start_date, "end_date": end_date, "departure_meter": dec(departure_meter), "return_meter": dec(return_meter), "notes": notes.strip() or None})
    except ValueError as exc:
        db.rollback(); raise HTTPException(400, str(exc))
    except Exception as exc:
        db.rollback(); raise HTTPException(400, f"تعذر تسجيل المهمة: {exc}")
    return RedirectResponse("/missions", 303)
