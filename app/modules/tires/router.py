from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.templating import get_module_templates
from app.database.session import get_db
from app.modules.equipment.models import Equipment
from app.modules.tires import services
from app.modules.users.models import User

router = APIRouter()
templates = get_module_templates("app/modules/tires/templates")


def _decimal(value: str | None):
    if value in (None, ""):
        return None
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=400, detail="قيمة العداد غير صالحة")


@router.get("/tires", response_class=HTMLResponse)
def tires_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return templates.TemplateResponse("tires.html", {"request": request, "user": current_user, "tires": services.list_tires(db), "stats": services.dashboard_stats(db), "positions": services.list_positions(db)})


@router.get("/tires/inventory", response_class=HTMLResponse)
def tire_inventory_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return templates.TemplateResponse("tire_inventory.html", {"request": request, "user": current_user, "items": services.inventory(db)})


@router.get("/tires/positions", response_class=HTMLResponse)
def tire_positions_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return templates.TemplateResponse("tire_positions.html", {"request": request, "user": current_user, "positions": services.list_positions(db)})


@router.post("/tires/positions")
def create_position(code: str = Form(...), name: str = Form(...), description: str = Form(""), sort_order: int = Form(0), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        services.add_position(db, {"code": code.strip(), "name": name.strip(), "description": description.strip() or None, "sort_order": sort_order})
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"تعذر إنشاء الموضع: {exc}")
    return RedirectResponse("/tires/positions", status_code=303)


@router.post("/tires")
def create_tire(serial_number: str = Form(...), brand: str = Form(""), model: str = Form(""), size: str = Form(""), manufacture_date: date | None = Form(None), expiry_date: date | None = Form(None), acquisition_document: str = Form(""), notes: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        services.add_tire(db, {"serial_number": serial_number.strip(), "brand": brand.strip() or None, "model": model.strip() or None, "size": size.strip() or None, "manufacture_date": manufacture_date, "expiry_date": expiry_date, "acquisition_document": acquisition_document.strip() or None, "notes": notes.strip() or None})
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"تعذر إنشاء الإطار: {exc}")
    return RedirectResponse("/tires", status_code=303)


@router.get("/tires/{tire_id}", response_class=HTMLResponse)
def tire_detail(request: Request, tire_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    tire = services.get_tire(db, tire_id)
    if not tire:
        raise HTTPException(status_code=404, detail="الإطار غير موجود")
    return templates.TemplateResponse("tire_detail.html", {"request": request, "user": current_user, "tire": tire, "state": services.current_state(db, tire_id), "history": services.movement_history(db, tire_id), "equipment": db.query(Equipment).order_by(Equipment.registration_number, Equipment.id).all(), "positions": services.list_positions(db)})


@router.post("/tires/{tire_id}/movements")
def create_movement(tire_id: int, movement_type: str = Form(...), movement_date: date = Form(...), equipment_id: int | None = Form(None), position_id: int | None = Form(None), meter_value: str | None = Form(None), document_number: str = Form(""), reason: str = Form(""), notes: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        services.add_movement(db, tire_id, {"movement_date": movement_date, "movement_type": movement_type, "equipment_id": equipment_id, "position_id": position_id, "meter_value": _decimal(meter_value), "document_number": document_number.strip() or None, "reason": reason.strip() or None, "notes": notes.strip() or None})
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"تعذر تسجيل الحركة: {exc}")
    return RedirectResponse(f"/tires/{tire_id}", status_code=303)


@router.get("/equipment/{equipment_id}/tires", response_class=HTMLResponse)
def equipment_tires_page(request: Request, equipment_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    equipment = db.query(Equipment).filter(Equipment.id == equipment_id).first()
    if not equipment:
        raise HTTPException(status_code=404, detail="العتاد غير موجود")
    return templates.TemplateResponse("equipment_tires.html", {"request": request, "user": current_user, "equipment": equipment, "items": services.installed_for_equipment(db, equipment_id)})
