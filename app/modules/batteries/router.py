from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.templating import get_module_templates
from app.database.session import get_db
from app.modules.batteries import services
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
    return templates.TemplateResponse("batteries.html", {"request": request, "user": current_user, "batteries": services.list_batteries(db), "stats": services.stats(db), "equipment": db.query(Equipment).order_by(Equipment.registration_number, Equipment.id).all()})


@router.post("/batteries")
def create_battery(serial_number: str = Form(...), brand: str = Form(""), model: str = Form(""), manufacture_date: date | None = Form(None), expiry_date: date | None = Form(None), acquisition_document: str = Form(""), notes: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        services.add_battery(db, {"serial_number": serial_number.strip(), "brand": brand.strip() or None, "model": model.strip() or None, "manufacture_date": manufacture_date, "expiry_date": expiry_date, "acquisition_document": acquisition_document.strip() or None, "notes": notes.strip() or None})
    except Exception as exc:
        db.rollback(); raise HTTPException(400, f"تعذر إنشاء البطارية: {exc}")
    return RedirectResponse("/batteries", 303)


@router.get("/batteries/{battery_id}", response_class=HTMLResponse)
def battery_detail(request: Request, battery_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    battery = db.query(services.Battery).filter(services.Battery.id == battery_id).first() if hasattr(services, "Battery") else None
    if not battery:
        from app.modules.batteries.models import Battery
        battery = db.query(Battery).filter(Battery.id == battery_id).first()
    if not battery:
        raise HTTPException(404, "البطارية غير موجودة")
    from app.modules.batteries.models import BatteryMovement
    history = db.query(BatteryMovement).filter(BatteryMovement.battery_id == battery_id).order_by(BatteryMovement.movement_date.desc(), BatteryMovement.id.desc()).all()
    return templates.TemplateResponse("battery_detail.html", {"request": request, "user": current_user, "battery": battery, "state": services.current_state(db, battery_id), "history": history, "equipment": db.query(Equipment).order_by(Equipment.registration_number, Equipment.id).all(), "today": date.today()})


@router.post("/batteries/{battery_id}/movements")
def create_movement(battery_id: int, movement_type: str = Form(...), movement_date: date = Form(...), equipment_id: int | None = Form(None), meter_value: str | None = Form(None), document_number: str = Form(""), reason: str = Form(""), notes: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        services.add_movement(db, battery_id, {"movement_date": movement_date, "movement_type": movement_type, "equipment_id": equipment_id, "meter_value": dec(meter_value), "document_number": document_number.strip() or None, "reason": reason.strip() or None, "notes": notes.strip() or None})
    except ValueError as exc:
        db.rollback(); raise HTTPException(400, str(exc))
    return RedirectResponse(f"/batteries/{battery_id}", 303)


@router.get("/equipment/{equipment_id}/batteries", response_class=HTMLResponse)
def equipment_battery_page(request: Request, equipment_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    equipment = db.query(Equipment).filter(Equipment.id == equipment_id).first()
    if not equipment:
        raise HTTPException(404, "العتاد غير موجود")
    items = []
    for battery in services.list_batteries(db):
        state = services.current_state(db, battery.id)
        if state and state["installed"] and state["equipment"] and state["equipment"].id == equipment_id:
            items.append(battery)
    return templates.TemplateResponse("equipment_batteries.html", {"request": request, "user": current_user, "equipment": equipment, "items": items})
