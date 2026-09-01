from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.templating import get_module_templates
from app.database.session import get_db
from app.modules.equipment.models import Equipment
from app.modules.fuel import services
from app.modules.fuel.models import FuelRecord
from app.modules.users.models import User

router = APIRouter()
templates = get_module_templates("app/modules/fuel/templates")


def dec(value: str):
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        raise HTTPException(400, "قيمة رقمية غير صالحة")


@router.get("/fuel", response_class=HTMLResponse)
def fuel_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    records = services.list_records(db)
    enriched = [{"record": r, "distance": services.distance_from_previous(db, r), "consumption": services.consumption(db, r), "abnormal": services.is_abnormal(db, r)} for r in records]
    return templates.TemplateResponse("fuel.html", {"request": request, "user": current_user, "records": enriched, "equipment": db.query(Equipment).order_by(Equipment.registration_number, Equipment.id).all(), "monthly": services.monthly_summary(db)})


@router.post("/fuel")
def create_fuel(equipment_id: int = Form(...), fueling_date: date = Form(...), meter_value: str = Form(...), quantity: str = Form(...), fuel_type: str = Form(""), document_number: str = Form(""), station: str = Form(""), notes: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        services.add_record(db, {"equipment_id": equipment_id, "fueling_date": fueling_date, "sequence_number": None, "meter_value": dec(meter_value), "quantity": dec(quantity), "fuel_type": fuel_type.strip() or None, "document_number": document_number.strip() or None, "station": station.strip() or None, "notes": notes.strip() or None})
    except ValueError as exc:
        db.rollback(); raise HTTPException(400, str(exc))
    except Exception as exc:
        db.rollback(); raise HTTPException(400, f"تعذر تسجيل التعبئة: {exc}")
    return RedirectResponse("/fuel", 303)


@router.get("/equipment/{equipment_id}/fuel", response_class=HTMLResponse)
def equipment_fuel_page(request: Request, equipment_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    equipment = db.query(Equipment).filter(Equipment.id == equipment_id).first()
    if not equipment:
        raise HTTPException(404, "العتاد غير موجود")
    records = db.query(FuelRecord).filter(FuelRecord.equipment_id == equipment_id).order_by(FuelRecord.fueling_date.desc(), FuelRecord.id.desc()).all()
    enriched = [{"record": r, "distance": services.distance_from_previous(db, r), "consumption": services.consumption(db, r), "abnormal": services.is_abnormal(db, r)} for r in records]
    return templates.TemplateResponse("equipment_fuel.html", {"request": request, "user": current_user, "equipment": equipment, "records": enriched, "average": services.equipment_average(db, equipment_id)})
