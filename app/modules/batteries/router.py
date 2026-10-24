from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload

from app.core.dependencies import get_current_user
from app.core.templating import get_module_templates
from app.database.session import get_db
from app.modules.asset_movements.mandatory_removal import require_explicit_removal, require_free_before_install
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
def batteries_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user), status_filter: str | None = Query(None, alias="filter")):
    validity_years = services.get_validity_years(db)
    batteries, states = services.current_states(db)
    statuses = {}
    due_dates = {}
    for battery in batteries:
        state = states.get(battery.id)
        equipment = state.get("equipment") if state else None
        statuses[battery.id] = services.status(
            battery, state, db=db, validity_years=validity_years
        )
        due_dates[battery.id] = services.replacement_due_date(
            db, battery, equipment, validity_years
        )
    from app.modules.spare_parts_requests.services import list_asset_receipts
    stats = services.stats(db, batteries, states, validity_years)
    filter_status = status_filter if status_filter in {"installed", "stock", "expired", "unassigned"} else None
    visible_batteries = [battery for battery in batteries if not filter_status or statuses[battery.id] == filter_status]
    filter_labels = {
        "installed": "البطاريات المركبة حاليًا",
        "stock": "البطاريات الموجودة في المخزون",
        "expired": "البطاريات المستحقة للاستبدال",
        "unassigned": "البطاريات غير المخصصة",
    }
    return templates.TemplateResponse(request=request, name="batteries.html", context={"request": request, "user": current_user, "batteries": visible_batteries, "stats": stats, "validity_years": validity_years, "statuses": statuses, "due_dates": due_dates, "battery_states": states, "battery_receipts": list_asset_receipts(db, "battery"), "filter_status": filter_status, "filter_label": filter_labels.get(filter_status)})


@router.get("/batteries/equipment", response_class=HTMLResponse)
def battery_equipment_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    equipment_rows = db.query(Equipment).options(joinedload(Equipment.equipment_model)).order_by(Equipment.registration_number, Equipment.id).all()
    batteries, states = services.current_states(db)
    installed_by_equipment = {}
    installed_batteries_by_equipment = {}
    for battery in batteries:
        state = states.get(battery.id)
        if not state or not state.get("installed") or not state.get("equipment"):
            continue
        equipment_id = state["equipment"].id
        installed_by_equipment[equipment_id] = installed_by_equipment.get(equipment_id, 0) + 1
        installed_batteries_by_equipment.setdefault(equipment_id, []).append(battery)

    rows = []
    validity_years = services.get_validity_years(db)
    for equipment in equipment_rows:
        model = equipment.equipment_model
        expected_count = model.battery_count_required if model and model.has_batteries else 0
        expected_capacity = model.battery_capacity_ah if model and model.has_batteries else None
        expected_voltage = model.battery_voltage_v if model and model.has_batteries else None
        missing_specs = []
        if not model:
            missing_specs.append("ربط العتاد بطراز")
        elif model.has_batteries:
            if not expected_count or expected_count <= 0:
                missing_specs.append("عدد البطاريات")
            if not expected_capacity or expected_capacity <= 0:
                missing_specs.append("سعة البطارية")
            if not expected_voltage or expected_voltage <= 0:
                missing_specs.append("جهد البطارية")
        installed_count = installed_by_equipment.get(equipment.id, 0)
        actual_batteries = installed_batteries_by_equipment.get(equipment.id, [])
        battery_lines = []
        for battery in actual_batteries:
            battery_state = states.get(battery.id)
            battery_lines.append({
                "battery": battery,
                "due_date": services.replacement_due_date(db, battery, equipment, validity_years),
                "status": services.status(battery, battery_state, equipment=equipment, db=db, validity_years=validity_years),
            })
        rows.append({
            "equipment": equipment,
            "model": model,
            "has_batteries": bool(model and model.has_batteries),
            "expected_count": expected_count,
            "expected_capacity": expected_capacity,
            "expected_voltage": expected_voltage,
            "installed_count": installed_count,
            "remaining_count": max(expected_count - installed_count, 0),
            "excess_count": max(installed_count - expected_count, 0),
            "installed_batteries": actual_batteries,
            "battery_lines": battery_lines,
            "missing_specs": missing_specs,
        })
    return templates.TemplateResponse(request=request, name="battery_equipment.html", context={"request": request, "user": current_user, "equipment_rows": rows})


@router.get("/batteries/settings", response_class=HTMLResponse)
def battery_settings_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return templates.TemplateResponse(request=request, name="battery_settings.html", context={"request": request, "user": current_user, "validity_years": services.get_validity_years(db)})


@router.post("/batteries/settings")
def update_battery_settings(validity_years: int = Form(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        services.set_validity_years(db, validity_years)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))
    return RedirectResponse("/batteries", 303)


@router.post("/batteries")
def create_battery(battery_type: str = Form(...), brand: str = Form(""), capacity: str = Form(""), manufacture_date: date | None = Form(None), receipt_date: date | None = Form(None), acquisition_document: str = Form(...), notes: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        services.add_battery(db, {"battery_type": battery_type.strip(), "brand": brand.strip() or None, "capacity": capacity.strip() or None, "manufacture_date": manufacture_date, "receipt_date": receipt_date, "acquisition_document": acquisition_document.strip(), "notes": notes.strip() or None})
    except Exception as exc:
        db.rollback()
        raise HTTPException(400, f"تعذر إنشاء البطارية: {exc}")
    return RedirectResponse("/batteries", 303)


@router.post("/batteries/{battery_id:int}/delete")
def delete_battery(battery_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        services.delete_battery(db, battery_id)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))
    return RedirectResponse("/batteries", 303)


@router.get("/batteries/{battery_id:int}", response_class=HTMLResponse)
def battery_detail(request: Request, battery_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    battery = db.query(Battery).filter(Battery.id == battery_id).first()
    if not battery:
        raise HTTPException(404, "البطارية غير موجودة")
    history = db.query(BatteryMovement).filter(BatteryMovement.battery_id == battery_id).order_by(BatteryMovement.movement_date.desc(), BatteryMovement.id.desc()).all()
    state = services.current_state(db, battery_id)
    equipment = state.get("equipment") if state else None
    return templates.TemplateResponse(request=request, name="battery_detail.html", context={"request": request, "user": current_user, "battery": battery, "state": state, "history": history, "equipment": db.query(Equipment).order_by(Equipment.registration_number, Equipment.id).all(), "current_equipment": equipment, "replacement_due_date": services.replacement_due_date(db, battery, equipment), "validity_years": services.get_validity_years(db), "today": date.today()})


@router.post("/batteries/{battery_id:int}/movements")
def create_movement(battery_id: int, movement_type: str = Form(...), movement_date: date = Form(...), equipment_id: int | None = Form(None), meter_value: str | None = Form(None), document_number: str = Form(""), reason: str = Form(""), notes: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        reason_value = reason.strip()
        require_explicit_removal(movement_type, reason_value, resource_label="البطارية")
        state = services.current_state(db, battery_id)
        require_free_before_install(movement_type=movement_type, currently_installed=bool(state and state.get("installed")), resource_label="البطارية")
        services.add_movement(db, battery_id, {"movement_date": movement_date, "movement_type": movement_type, "equipment_id": equipment_id, "meter_value": dec(meter_value), "document_number": document_number.strip() or None, "reason": reason_value or None, "notes": notes.strip() or None})
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
    movements = db.query(BatteryMovement).options(joinedload(BatteryMovement.battery)).order_by(BatteryMovement.battery_id.asc(), BatteryMovement.movement_date.asc(), BatteryMovement.id.asc()).all()
    current_equipment_by_battery = {}
    history = []
    for movement in movements:
        if movement.movement_type in {"install", "move"}:
            current_equipment_by_battery[movement.battery_id] = movement.equipment_id
            if movement.equipment_id == equipment_id:
                history.append(movement)
        elif movement.movement_type == "remove":
            was_on_equipment = current_equipment_by_battery.get(movement.battery_id) == equipment_id
            if was_on_equipment or movement.equipment_id == equipment_id:
                history.append(movement)
            current_equipment_by_battery[movement.battery_id] = None
    history.sort(key=lambda movement: (movement.movement_date, movement.id), reverse=True)
    return templates.TemplateResponse(request=request, name="equipment_batteries.html", context={"request": request, "user": current_user, "equipment": equipment, "items": items, "due_dates": due_dates, "statuses": statuses, "validity_years": services.get_validity_years(db), "history": history})
