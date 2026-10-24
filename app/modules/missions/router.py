from datetime import date
from decimal import Decimal, InvalidOperation
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session, joinedload
from app.core.dependencies import get_current_user
from app.core.permissions import Role
from app.core.templating import get_module_templates
from app.database.session import get_db
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentModel
from app.modules.missions import services
from app.modules.missions.models import Driver
from app.modules.users.models import User

router = APIRouter()
templates = get_module_templates("app/modules/missions/templates")


def dec(value):
    if not value: return None
    try: return Decimal(value)
    except (InvalidOperation, ValueError): raise HTTPException(400, "قيمة العداد غير صالحة")


@router.get("/missions", response_class=HTMLResponse)
def missions_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    services.sync_mission_statuses(db)
    drivers = services.list_drivers(db)
    today = date.today()
    equipment = (
        db.query(Equipment)
        .options(joinedload(Equipment.equipment_model))
        .order_by(Equipment.registration_number, Equipment.id)
        .all()
    )
    return templates.TemplateResponse(request=request, name="missions.html", context={"request": request, "user": current_user, "equipment": equipment, "drivers": services.list_active_assigned_drivers(db), "driver_equipment": _driver_equipment_options(db), "counts": services.counts(db), "license_expiry_alerts": services.license_expiry_alerts(drivers, today=today), "today": today})


@router.get("/missions/records", response_class=HTMLResponse)
def mission_records_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    services.sync_mission_statuses(db)
    missions = [{"mission": m, "status": services.mission_status(m)} for m in services.list_missions(db)]
    return templates.TemplateResponse(request=request, name="mission_records.html", context={"request": request, "user": current_user, "missions": missions})


def _driver_equipment_options(db: Session):
    return (
        db.query(Equipment)
        .join(EquipmentModel, Equipment.equipment_model_id == EquipmentModel.id)
        .options(joinedload(Equipment.equipment_model))
        .filter(EquipmentModel.requires_driver.is_(True))
        .order_by(Equipment.registration_number, Equipment.id)
        .all()
    )


def _unassigned_driver_equipment(db: Session):
    assigned_driver = db.query(Driver.id).filter(
        Driver.is_active.is_(True),
        Driver.assigned_equipment_id == Equipment.id,
    )
    return (
        db.query(Equipment)
        .join(EquipmentModel, Equipment.equipment_model_id == EquipmentModel.id)
        .options(
            joinedload(Equipment.equipment_model),
            joinedload(Equipment.equipment_type),
        )
        .filter(
            EquipmentModel.requires_driver.is_(True),
            ~assigned_driver.exists(),
        )
        .order_by(Equipment.registration_number, Equipment.id)
        .all()
    )


@router.get("/missions/drivers", response_class=HTMLResponse)
def drivers_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    setting = services.get_driver_system_setting(db)
    drivers = services.list_drivers(db)
    return templates.TemplateResponse(
        request=request,
        name="drivers.html",
        context={
            "request": request,
            "user": current_user,
            "drivers": drivers,
            "equipment": _driver_equipment_options(db),
            "unassigned_equipment": _unassigned_driver_equipment(db),
            "center_column_label": setting.center_column_label,
        },
    )


@router.get("/missions/drivers/{driver_id}", response_class=HTMLResponse)
def driver_history_page(
    driver_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    driver = services.get_driver(db, driver_id)
    if not driver:
        raise HTTPException(404, "السائق غير موجود")
    missions, legacy_match_count = services.list_driver_missions(db, driver)
    return templates.TemplateResponse(
        request=request,
        name="driver_history.html",
        context={
            "request": request,
            "user": current_user,
            "driver": driver,
            "missions": missions,
            "legacy_match_count": legacy_match_count,
        },
    )


@router.post("/missions/drivers/settings/center-column-label")
def update_center_column_label(
    center_column_label: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != Role.ADMIN.value:
        raise HTTPException(403, "تغيير تسمية العمود متاح لمدير النظام فقط")
    try:
        services.set_center_column_label(
            db, center_column_label, user_id=current_user.id
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))
    return RedirectResponse("/missions/drivers", 303)


@router.post("/missions/drivers")
def create_driver(
    employee_number: str = Form(""),
    first_name: str = Form(...),
    last_name: str = Form(...),
    center: str = Form(""),
    license_class: str = Form(...),
    license_issue_date: date | None = Form(None),
    license_expiry_date: date | None = Form(None),
    assigned_equipment_id: int | None = Form(None),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        services.create_driver(db, {
            "employee_number": employee_number,
            "first_name": first_name,
            "last_name": last_name,
            "center": center,
            "license_class": license_class,
            "license_issue_date": license_issue_date,
            "license_expiry_date": license_expiry_date,
            "assigned_equipment_id": assigned_equipment_id,
            "notes": notes,
        })
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))
    return RedirectResponse("/missions/drivers", 303)


@router.get("/missions/drivers/{driver_id}/edit", response_class=HTMLResponse)
def edit_driver_page(
    driver_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    driver = services.get_driver(db, driver_id)
    if not driver:
        raise HTTPException(404, "السائق غير موجود")
    equipment = _driver_equipment_options(db)
    if (
        driver.assigned_equipment
        and all(item.id != driver.assigned_equipment.id for item in equipment)
    ):
        equipment.append(driver.assigned_equipment)
    return templates.TemplateResponse(
        request=request,
        name="driver_form.html",
        context={
            "request": request,
            "user": current_user,
            "driver": driver,
            "equipment": equipment,
        },
    )


@router.post("/missions/drivers/{driver_id}/edit")
def update_driver(
    driver_id: int,
    employee_number: str = Form(""),
    first_name: str = Form(...),
    last_name: str = Form(...),
    center: str = Form(""),
    license_class: str = Form(...),
    license_issue_date: date | None = Form(None),
    license_expiry_date: date | None = Form(None),
    assigned_equipment_id: int | None = Form(None),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        services.update_driver(db, driver_id, {
            "employee_number": employee_number,
            "first_name": first_name,
            "last_name": last_name,
            "center": center,
            "license_class": license_class,
            "license_issue_date": license_issue_date,
            "license_expiry_date": license_expiry_date,
            "assigned_equipment_id": assigned_equipment_id,
            "notes": notes,
        })
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))
    return RedirectResponse("/missions/drivers", 303)


@router.post("/missions/drivers/{driver_id}/status")
def change_driver_status(
    driver_id: int,
    is_active: bool = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        services.set_driver_active(db, driver_id, is_active)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(404, str(exc))
    return RedirectResponse("/missions/drivers", 303)


@router.post("/missions")
def create_mission(equipment_id: int = Form(...), driver_id: int | None = Form(None), driver_name: str = Form(""), mission_document: str = Form(""), purpose: str = Form(""), destination: str = Form(""), start_date: date = Form(...), end_date: date | None = Form(None), departure_meter: str | None = Form(None), return_meter: str | None = Form(None), notes: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        services.add_mission(db, {"equipment_id": equipment_id, "driver_id": driver_id, "driver_name": driver_name.strip() or None, "mission_document": mission_document.strip() or None, "purpose": purpose.strip() or None, "destination": destination.strip() or None, "start_date": start_date, "end_date": end_date, "departure_meter": dec(departure_meter), "return_meter": dec(return_meter), "notes": notes.strip() or None})
    except ValueError as exc:
        db.rollback(); raise HTTPException(400, str(exc))
    except Exception as exc:
        db.rollback(); raise HTTPException(400, f"تعذر تسجيل المهمة: {exc}")
    return RedirectResponse("/missions", 303)
