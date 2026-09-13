from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.templating import get_module_templates
from app.database.session import get_db
from app.modules.batteries import services
from app.modules.batteries.models import Battery, BatteryMovement
from app.modules.equipment.models import Equipment
from app.modules.users.models import User

router = APIRouter()
templates = get_module_templates("app/modules/batteries/templates")


def dec(v):
    if not v:
        return None
    try:
        return Decimal(v)
    except (InvalidOperation, ValueError):
        raise HTTPException(400, "قيمة العداد غير صالحة")


@router.get("/batteries", response_class=HTMLResponse)
def batteries_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    batteries, states = services.current_states(db)
    statuses = {}
    due_dates = {}
    for battery in batteries:
        state = states.get(battery.id)
        equipment = state.get("equipment") if state else None
        statuses[battery.id] = services.status(battery, state, db=db)
        due_dates[battery.id] = services.replacement_due_date(db, battery, equipment)
    return templates.TemplateResponse("batteries.html", {"request": request, "user": current_user, "batteries": batteries, "stats": services.stats(db), "validity_years": services.get_validity_years(db), "statuses": statuses, "due_dates": due_dates})


@router.get("/batteries/settings", response_class=HTMLResponse)
def battery_settings_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return templates.TemplateResponse("battery_settings.html", {"request": request, "user": current_user, "validity_years": services.get_validity_years(db)})


@router.post("/batteries/settings")
def update_battery_settings(validity_years: int = Form(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        services.set_validity_years(db, validity_years)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))
    return RedirectResponse("/batteries", 303)


@router.post("/batteries")
def create_battery(serial_number: str = Form(...), brand: str = Form(""), model: str = Form(""), manufacture_date: date | None = Form(None), receipt_date: date | None = Form(None), acquisition_document: str = Form(""), notes: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        services.add_battery(db, {"serial_number": serial_number.strip(), "brand": brand.strip() or None, "model": model.strip() or None, "manufacture_date": manufacture_date, "receipt_date": receipt_date, "acquisition_document": acquisition_document.strip() or None, "notes": notes.strip() or None})
    except Exception as exc:
        db.rollback()
        raise HTTPException(400, f"تعذر إنشاء البطارية: {exc}")
    return RedirectResponse("/batteries", 303)


@router.get("/batteries/{battery_id}", response_class=HTMLResponse)
def battery_detail(request: Request, battery_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    battery = db.query(Battery).filter(Battery.id == battery_id).first()
    if not battery:
        raise HTTPException(404, "البطارية غير موجودة")
    history = db.query(BatteryMovement).filter(BatteryMovement.battery_id == battery_id).order_by(BatteryMovement.movement_date.desc(), BatteryMovement.id.desc()).all()
    state = services.current_state(db, battery_id)
    equipment = state.get("equipment") if state else None
    return templates.TemplateResponse("battery_detail.html", {"request": request, "user": current_user, "battery": battery, "state": state, "history": history, "equipment": db.query(Equipment).order_by(Equipment.registration_number, Equipment.id).all(), "current_equipment": equipment, "replacement_due_date": services.replacement_due_date(db, battery, equipment), "validity_years": services.get_validity_years(db), "today": date.today()})


@router.post("/batteries/{battery_id}/movements")
def create_movement(battery_id: int, movement_type: str = Form(...), movement_date: date = Form(...), equipment_id: int | None = Form(None), meter_value: str | None = Form(None), document_number: str = Form(""), reason: str = Form(""), notes: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        services.add_movement(db, battery_id, {"movement_date": movement_date, "movement_type": movement_type, "equipment_id": equipment_id, "meter_value": dec(meter_value), "document_number": document_number.strip() or None, "reason": reason.strip() or None, "notes": notes.strip() or None})
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))
    except Exception as exc:
        db.rollback()
        raise HTTPException(400, f"تعذر تسجيل الحركة: {exc}")
    return RedirectResponse(f"/batteries/{battery_id}", 303)


@router.get("/equipment/{equipment_id}/batteries", response_class=HTMLResponse)
def equipment_battery_page(request: Request, equipment_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    equipment = db.query(Equipment).filter(Equipment.id == equipment_id).first()
    if not equipment:
        raise HTTPException(404, "العتاد غير موجود")
    batteries, states = services.current_states(db)
    items = []
    due_dates = {}
    statuses = {}
    for battery in batteries:
        state = states.get(battery.id)
        if state and state["installed"] and state["equipment"] and state["equipment"].id == equipment_id:
            items.append(battery)
            due_dates[battery.id] = services.replacement_due_date(db, battery, equipment)
            statuses[battery.id] = services.status(battery, state, equipment=equipment, db=db)
    return templates.TemplateResponse("equipment_batteries.html", {"request": request, "user": current_user, "equipment": equipment, "items": items, "due_dates": due_dates, "statuses": statuses, "validity_years": services.get_validity_years(db)})