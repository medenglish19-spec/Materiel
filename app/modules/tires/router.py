from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.templating import get_module_templates
from app.database.session import get_db
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentModel
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


def _error(exc: Exception):
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/tires", response_class=HTMLResponse)
def tires_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    tires = services.list_tires(db)
    statuses = {t.id: services.tire_status(t, services.current_state(db, t.id)) for t in tires}
    return templates.TemplateResponse("tires.html", {"request": request, "user": current_user, "tires": tires, "stats": services.dashboard_stats(db), "validity_years": services.get_validity_years(db), "tire_statuses": statuses})


@router.get("/tires/settings", response_class=HTMLResponse)
def tire_settings_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return templates.TemplateResponse("tire_settings.html", {"request": request, "user": current_user, "validity_years": services.get_validity_years(db)})


@router.post("/tires/settings")
def update_tire_settings(validity_years: int = Form(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        services.set_validity_years(db, validity_years)
    except ValueError as exc:
        db.rollback()
        raise _error(exc)
    return RedirectResponse("/tires/settings", status_code=303)


@router.get("/tires/inventory", response_class=HTMLResponse)
def tire_inventory_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return templates.TemplateResponse("tire_inventory.html", {"request": request, "user": current_user, "items": services.inventory(db)})


@router.get("/tires/positions", response_class=HTMLResponse)
def tire_positions_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    models = db.query(EquipmentModel).order_by(EquipmentModel.name).all()
    return templates.TemplateResponse("tire_positions.html", {"request": request, "user": current_user, "models": models})


@router.get("/tires/models/{model_id}/configuration", response_class=HTMLResponse)
def tire_model_configuration(request: Request, model_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    configuration = services.model_configuration(db, model_id)
    if not configuration:
        raise HTTPException(status_code=404, detail="الطراز غير موجود")
    return templates.TemplateResponse("tire_model_configuration.html", {"request": request, "user": current_user, **configuration})


@router.post("/tires/models/{model_id}/sizes")
def create_model_size(model_id: int, size: str = Form(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        services.add_model_size(db, model_id, size)
    except ValueError as exc:
        db.rollback()
        raise _error(exc)
    return RedirectResponse(f"/tires/models/{model_id}/configuration", status_code=303)


@router.post("/tires/models/{model_id}/positions")
def create_model_position(model_id: int, axle_number: int = Form(...), side: str = Form(...), position_type: str = Form(...), description: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        services.add_position(db, model_id, axle_number, side, position_type, description)
    except ValueError as exc:
        db.rollback()
        raise _error(exc)
    return RedirectResponse(f"/tires/models/{model_id}/configuration", status_code=303)


@router.post("/tires/positions/{position_id}/delete")
def delete_model_position(position_id: int, model_id: int = Form(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        services.delete_position(db, position_id)
    except ValueError as exc:
        db.rollback()
        raise _error(exc)
    return RedirectResponse(f"/tires/models/{model_id}/configuration", status_code=303)


@router.post("/tires/model-sizes/{size_id}/delete")
def delete_model_size(size_id: int, model_id: int = Form(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    services.delete_model_size(db, size_id)
    return RedirectResponse(f"/tires/models/{model_id}/configuration", status_code=303)


@router.post("/tires")
def create_tire(serial_number: str = Form(...), brand: str = Form(""), model: str = Form(""), size: str = Form(""), manufacture_date: date | None = Form(None), receipt_date: date | None = Form(None), acquisition_document: str = Form(""), notes: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        services.add_tire(db, {"serial_number": serial_number.strip(), "brand": brand.strip() or None, "model": model.strip() or None, "size": size.strip() or None, "manufacture_date": manufacture_date, "receipt_date": receipt_date, "acquisition_document": acquisition_document.strip() or None, "notes": notes.strip() or None})
    except Exception as exc:
        db.rollback()
        raise _error(exc)
    return RedirectResponse("/tires", status_code=303)


@router.get("/tires/{tire_id}", response_class=HTMLResponse)
def tire_detail(request: Request, tire_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    tire = services.get_tire(db, tire_id)
    if not tire:
        raise HTTPException(status_code=404, detail="الإطار غير موجود")
    state = services.current_state(db, tire_id)
    equipment = db.query(Equipment).order_by(Equipment.registration_number, Equipment.id).all()
    all_positions = services.list_positions(db)
    return templates.TemplateResponse("tire_detail.html", {"request": request, "user": current_user, "tire": tire, "state": state, "history": services.movement_history(db, tire_id), "equipment": equipment, "positions": all_positions, "today": date.today(), "validity_years": services.get_validity_years(db)})


@router.post("/tires/{tire_id}/movements")
def create_movement(tire_id: int, movement_type: str = Form(...), movement_date: date = Form(...), equipment_id: int | None = Form(None), position_id: int | None = Form(None), meter_value: str | None = Form(None), document_number: str = Form(""), reason: str = Form(""), notes: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        services.add_movement(db, tire_id, {"movement_date": movement_date, "movement_type": movement_type, "equipment_id": equipment_id, "position_id": position_id, "meter_value": _decimal(meter_value), "document_number": document_number.strip() or None, "reason": reason.strip() or None, "notes": notes.strip() or None})
    except ValueError as exc:
        db.rollback()
        raise _error(exc)
    except Exception as exc:
        db.rollback()
        raise _error(exc)
    return RedirectResponse(f"/tires/{tire_id}", status_code=303)


@router.post("/tires/{tire_id}/dispose")
def dispose_tire(tire_id: int, disposal_date: date = Form(...), disposal_document: str = Form(...), reason: str = Form(...), notes: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        services.dispose_tire(db, tire_id, disposal_date, disposal_document, reason, notes)
    except ValueError as exc:
        db.rollback()
        raise _error(exc)
    return RedirectResponse(f"/tires/{tire_id}", status_code=303)


@router.get("/equipment/{equipment_id}/tires", response_class=HTMLResponse)
def equipment_tires_page(request: Request, equipment_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    equipment = db.query(Equipment).filter(Equipment.id == equipment_id).first()
    if not equipment:
        raise HTTPException(status_code=404, detail="العتاد غير موجود")
    model = db.query(EquipmentModel).filter(EquipmentModel.id == equipment.equipment_model_id).first()
    return templates.TemplateResponse("equipment_tires.html", {"request": request, "user": current_user, "equipment": equipment, "model": model, "items": services.installed_for_equipment(db, equipment_id), "positions": services.list_positions(db, equipment.equipment_model_id)})
