from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session, joinedload

from app.core.dependencies import get_current_user
from app.core.templating import get_module_templates
from app.database.session import get_db
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentType
from app.modules.meter_readings.models import MeterReading
from app.modules.users.models import User
from app.modules.maintenance.models import MaintenanceRecord, MaintenanceRule

router = APIRouter()
templates = get_module_templates("app/modules/maintenance/templates")


def latest_readings(db: Session):
    readings = {}
    rows = db.query(MeterReading).order_by(
        MeterReading.equipment_id,
        desc(MeterReading.reading_date),
        desc(MeterReading.id),
    ).all()
    for row in rows:
        if row.equipment_id not in readings:
            readings[row.equipment_id] = row
    return readings


def latest_records(db: Session):
    result = {}
    rows = db.query(MaintenanceRecord).order_by(
        MaintenanceRecord.equipment_id,
        MaintenanceRecord.rule_id,
        desc(MaintenanceRecord.maintenance_date),
        desc(MaintenanceRecord.id),
    ).all()
    for row in rows:
        key = (row.equipment_id, row.rule_id)
        if key not in result:
            result[key] = row
    return result


def measurement_unit(equipment):
    """The equipment type is the single source of truth for the meter unit."""
    return (equipment.equipment_type.measurement_unit or "").strip().lower()


def current_meter_value(equipment, reading):
    """Return the current meter using the equipment type's configured unit."""
    unit = measurement_unit(equipment)
    if reading is not None:
        if unit == "hours" and reading.hours is not None:
            return reading.hours
        if unit == "km" and reading.odometer is not None:
            return reading.odometer
    if unit == "hours":
        return equipment.current_hours
    return equipment.current_odometer


def status_for(rule, equipment, record, current_value):
    if record is None:
        return "بلا سجل", "neutral", None

    unit = measurement_unit(equipment)
    interval = rule.interval_hours if unit == "hours" else rule.interval_km
    warning = rule.warning_km

    remaining = None
    if interval is not None and current_value is not None and record.meter_value is not None:
        due_value = Decimal(str(record.meter_value)) + Decimal(str(interval))
        remaining = due_value - Decimal(str(current_value))
        if remaining <= 0:
            return "مستحقة الآن", "danger", remaining
        if warning is not None and remaining <= Decimal(str(warning)):
            return "قريبة", "warning", remaining

    if rule.interval_days is not None:
        due_date = record.maintenance_date + timedelta(days=int(rule.interval_days))
        days_left = (due_date - date.today()).days
        if days_left <= 0:
            return "مستحقة الآن", "danger", remaining
        if rule.warning_days is not None and days_left <= int(rule.warning_days):
            return "قريبة", "warning", remaining

    return "سليمة", "success", remaining


@router.get("/maintenance", response_class=HTMLResponse)
def maintenance_dashboard_page(
    request: Request,
    current_user: User = Depends(get_current_user),
):
    return templates.TemplateResponse(
        "maintenance_home.html",
        {"request": request, "user": current_user},
    )


@router.get("/maintenance/periodic", response_class=HTMLResponse)
def periodic_maintenance_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    equipment = db.query(Equipment).options(joinedload(Equipment.equipment_type)).order_by(
        Equipment.registration_number, Equipment.asset_code
    ).all()
    rules = db.query(MaintenanceRule).options(joinedload(MaintenanceRule.equipment_type)).filter(
        MaintenanceRule.is_active.is_(True)
    ).order_by(MaintenanceRule.id).all()
    readings = latest_readings(db)
    records = latest_records(db)
    rows = []
    counts = {"total": 0, "danger": 0, "warning": 0, "success": 0, "neutral": 0}

    for eq in equipment:
        current = readings.get(eq.id)
        current_value = current_meter_value(eq, current)
        for rule in rules:
            if rule.equipment_type_id != eq.equipment_type_id:
                continue
            rec = records.get((eq.id, rule.id))
            state, css, remaining = status_for(rule, eq, rec, current_value)
            counts["total"] += 1
            counts[css] += 1

            unit = measurement_unit(eq)
            interval = rule.interval_hours if unit == "hours" else rule.interval_km
            next_meter = (
                Decimal(str(rec.meter_value)) + Decimal(str(interval))
                if rec and rec.meter_value is not None and interval is not None
                else None
            )
            next_date = (
                rec.maintenance_date + timedelta(days=int(rule.interval_days))
                if rec and rule.interval_days
                else None
            )
            rows.append({
                "equipment": eq,
                "rule": rule,
                "record": rec,
                "current": current_value,
                "unit": unit,
                "next_meter": next_meter,
                "next_date": next_date,
                "remaining": remaining,
                "state": state,
                "css": css,
            })

    return templates.TemplateResponse(
        "maintenance_dashboard.html",
        {"request": request, "user": current_user, "rows": rows, "counts": counts},
    )


@router.get("/maintenance/rules", response_class=HTMLResponse)
def maintenance_rules_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rules = db.query(MaintenanceRule).options(joinedload(MaintenanceRule.equipment_type)).order_by(MaintenanceRule.id.desc()).all()
    types = db.query(EquipmentType).order_by(EquipmentType.name).all()
    return templates.TemplateResponse("maintenance_rules.html", {"request": request, "user": current_user, "rules": rules, "types": types})


@router.post("/maintenance/rules/create")
def maintenance_rule_create(
    name: str = Form(...), equipment_type_id: int = Form(...), interval_km: str = Form(""), interval_hours: str = Form(""), interval_days: str = Form(""), warning_km: str = Form("1000"), warning_days: str = Form("30"), description: str = Form(""),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    def dec(v):
        try:
            return Decimal(v) if v else None
        except (InvalidOperation, ValueError):
            return None

    equipment_type = db.query(EquipmentType).filter(EquipmentType.id == equipment_type_id).first()
    if equipment_type is None:
        return RedirectResponse("/maintenance/rules", status_code=status.HTTP_303_SEE_OTHER)

    km = dec(interval_km)
    hours = dec(interval_hours)
    days = int(interval_days) if interval_days else None

    if equipment_type.measurement_unit == "km":
        hours = None
    elif equipment_type.measurement_unit == "hours":
        km = None

    rule = MaintenanceRule(
        name=name.strip(),
        equipment_type_id=equipment_type_id,
        interval_km=km,
        interval_hours=hours,
        interval_days=days,
        warning_km=dec(warning_km),
        warning_days=int(warning_days) if warning_days else None,
        description=description.strip() or None,
    )
    db.add(rule)
    db.commit()
    return RedirectResponse("/maintenance/rules", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/maintenance/records", response_class=HTMLResponse)
def maintenance_records_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    records = db.query(MaintenanceRecord).options(
        joinedload(MaintenanceRecord.equipment), joinedload(MaintenanceRecord.rule)
    ).order_by(desc(MaintenanceRecord.maintenance_date), desc(MaintenanceRecord.id)).all()
    equipment = db.query(Equipment).order_by(Equipment.registration_number, Equipment.asset_code).all()
    rules = db.query(MaintenanceRule).filter(MaintenanceRule.is_active.is_(True)).order_by(MaintenanceRule.name).all()
    return templates.TemplateResponse("maintenance_records.html", {"request": request, "user": current_user, "records": records, "equipment": equipment, "rules": rules})


@router.post("/maintenance/records/create")
def maintenance_record_create(
    equipment_id: int = Form(...), rule_id: int = Form(...), maintenance_date: date = Form(...), meter_value: str = Form(""), work_order: str = Form(""), workshop: str = Form(""), description: str = Form(""),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    equipment = db.query(Equipment).options(joinedload(Equipment.equipment_type)).filter(Equipment.id == equipment_id).first()
    rule = db.query(MaintenanceRule).filter(MaintenanceRule.id == rule_id, MaintenanceRule.is_active.is_(True)).first()
    if equipment is None or rule is None or rule.equipment_type_id != equipment.equipment_type_id:
        return RedirectResponse("/maintenance/records", status_code=status.HTTP_303_SEE_OTHER)

    unit = measurement_unit(equipment)
    meter = None
    if meter_value:
        try:
            meter = Decimal(meter_value)
        except (InvalidOperation, ValueError):
            return RedirectResponse("/maintenance/records", status_code=status.HTTP_303_SEE_OTHER)

    # A meter-based rule must carry the meter value used as the reference for the next service.
    if (unit == "km" and rule.interval_km is not None) or (unit == "hours" and rule.interval_hours is not None):
        if meter is None:
            return RedirectResponse("/maintenance/records", status_code=status.HTTP_303_SEE_OTHER)

    rec = MaintenanceRecord(
        equipment_id=equipment_id,
        rule_id=rule_id,
        maintenance_date=maintenance_date,
        meter_value=meter,
        work_order=work_order.strip() or None,
        workshop=workshop.strip() or None,
        description=description.strip() or None,
        status="completed",
    )
    db.add(rec)
    db.commit()
    return RedirectResponse("/maintenance/records", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/maintenance/due", response_class=HTMLResponse)
def maintenance_due_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    equipment = db.query(Equipment).options(joinedload(Equipment.equipment_type)).all()
    rules = db.query(MaintenanceRule).filter(MaintenanceRule.is_active.is_(True)).all()
    readings = latest_readings(db)
    records = latest_records(db)
    due_rows = []

    for eq in equipment:
        current = readings.get(eq.id)
        current_value = current_meter_value(eq, current)
        for rule in rules:
            if rule.equipment_type_id != eq.equipment_type_id:
                continue
            rec = records.get((eq.id, rule.id))
            state, css, remaining = status_for(rule, eq, rec, current_value)
            if state in ("مستحقة الآن", "قريبة", "بلا سجل"):
                due_rows.append({
                    "equipment": eq,
                    "rule": rule,
                    "record": rec,
                    "current": current_value,
                    "unit": measurement_unit(eq),
                    "remaining": remaining,
                    "state": state,
                    "css": css,
                })

    return templates.TemplateResponse("maintenance_due.html", {"request": request, "user": current_user, "rows": due_rows})
