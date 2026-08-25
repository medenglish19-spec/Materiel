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
    rows = db.query(MeterReading).order_by(MeterReading.equipment_id, desc(MeterReading.reading_date), desc(MeterReading.id)).all()
    for row in rows:
        if row.equipment_id not in readings:
            readings[row.equipment_id] = row
    return readings


def latest_records(db: Session):
    result = {}
    rows = db.query(MaintenanceRecord).order_by(MaintenanceRecord.equipment_id, MaintenanceRecord.rule_id, desc(MaintenanceRecord.maintenance_date), desc(MaintenanceRecord.id)).all()
    for row in rows:
        key = (row.equipment_id, row.rule_id)
        if key not in result:
            result[key] = row
    return result


def measurement_unit(equipment):
    return (equipment.equipment_type.measurement_unit or "").strip().lower()


def current_meter_value(equipment, reading):
    unit = measurement_unit(equipment)
    if unit == "hours":
        return equipment.current_hours if equipment.current_hours is not None else (reading.hours if reading else None)
    return equipment.current_odometer if equipment.current_odometer is not None else (reading.odometer if reading else None)


def chronology_error(db: Session, equipment_id: int, maintenance_date: date, meter: Decimal | None):
    """Reject a maintenance entry that breaks the vehicle's historical meter chronology."""
    if meter is None:
        return None
    records = db.query(MaintenanceRecord).filter(
        MaintenanceRecord.equipment_id == equipment_id,
        MaintenanceRecord.meter_value.is_not(None),
    ).order_by(MaintenanceRecord.maintenance_date, MaintenanceRecord.id).all()
    for row in records:
        if row.maintenance_date < maintenance_date and meter < Decimal(str(row.meter_value)):
            return "قراءة العداد أقل من قراءة سجل صيانة أقدم"
        if row.maintenance_date > maintenance_date and meter > Decimal(str(row.meter_value)):
            return "قراءة العداد أكبر من قراءة سجل صيانة أحدث"
    return None


def contradiction_for(equipment, record, current_value, db):
    if record is None or record.meter_value is None:
        return None
    error = chronology_error(db, equipment.id, record.maintenance_date, Decimal(str(record.meter_value)))
    if error:
        return f"⚠ {error}"
    if current_value is not None and record.meter_value > current_value:
        return "⚠ آخر صيانة تحمل عدادًا أكبر من العداد الحالي"
    return None


def status_for(rule, equipment, record, current_value):
    if record is None:
        return "بلا سجل", "neutral", None, {"remaining_days": None, "next_meter": None, "next_date": None}
    unit = measurement_unit(equipment)
    interval = rule.interval_hours if unit == "hours" else rule.interval_km
    warning_meter = rule.warning_km if unit == "km" else None
    remaining_meter = None
    remaining_days = None
    next_meter = None
    next_date = None
    if interval is not None and current_value is not None and record.meter_value is not None:
        next_meter = Decimal(str(record.meter_value)) + Decimal(str(interval))
        remaining_meter = next_meter - Decimal(str(current_value))
    if rule.interval_days is not None:
        next_date = record.maintenance_date + timedelta(days=int(rule.interval_days))
        remaining_days = (next_date - date.today()).days
    overdue_meter = remaining_meter is not None and remaining_meter <= 0
    overdue_days = remaining_days is not None and remaining_days <= 0
    near_meter = warning_meter is not None and remaining_meter is not None and remaining_meter <= Decimal(str(warning_meter))
    near_days = rule.warning_days is not None and remaining_days is not None and remaining_days <= int(rule.warning_days)
    if overdue_meter or overdue_days:
        return "مستحقة الآن", "danger", remaining_meter, {"remaining_days": remaining_days, "next_meter": next_meter, "next_date": next_date}
    if near_meter or near_days:
        return "تقترب", "warning", remaining_meter, {"remaining_days": remaining_days, "next_meter": next_meter, "next_date": next_date}
    return "ضمن الموعد", "success", remaining_meter, {"remaining_days": remaining_days, "next_meter": next_meter, "next_date": next_date}


def priority_for(state, remaining_meter, meta):
    if state == "مستحقة الآن": return 1
    if state == "تقترب": return 2
    if state == "بلا سجل": return 3
    candidates = [x for x in (remaining_meter, meta.get("remaining_days")) if x is not None]
    return 4 if candidates else 5


@router.get("/maintenance", response_class=HTMLResponse)
def maintenance_dashboard_page(request: Request, current_user: User = Depends(get_current_user)):
    return templates.TemplateResponse("maintenance_home.html", {"request": request, "user": current_user})


@router.get("/maintenance/periodic", response_class=HTMLResponse)
def periodic_maintenance_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    equipment = db.query(Equipment).options(joinedload(Equipment.equipment_type), joinedload(Equipment.equipment_model)).order_by(Equipment.registration_number, Equipment.asset_code).all()
    rules = db.query(MaintenanceRule).options(joinedload(MaintenanceRule.equipment_type)).filter(MaintenanceRule.is_active.is_(True)).order_by(MaintenanceRule.id).all()
    readings = latest_readings(db); records = latest_records(db)
    rows = []; counts = {"total": 0, "danger": 0, "warning": 0, "success": 0, "neutral": 0}
    for eq in equipment:
        current_value = current_meter_value(eq, readings.get(eq.id))
        for rule in rules:
            if rule.equipment_type_id != eq.equipment_type_id: continue
            rec = records.get((eq.id, rule.id)); state, css, remaining, meta = status_for(rule, eq, rec, current_value)
            counts["total"] += 1; counts[css] += 1
            rows.append({"equipment": eq, "rule": rule, "record": rec, "current": current_value, "unit": measurement_unit(eq), "next_meter": meta.get("next_meter"), "next_date": meta.get("next_date"), "remaining": remaining, "remaining_days": meta.get("remaining_days"), "state": state, "css": css, "priority": priority_for(state, remaining, meta), "contradiction": contradiction_for(eq, rec, current_value, db)})
    rows.sort(key=lambda r: (r["priority"], r["remaining"] if r["remaining"] is not None else Decimal("999999999"), r["remaining_days"] if r["remaining_days"] is not None else 999999999, r["equipment"].registration_number or r["equipment"].asset_code or ""))
    return templates.TemplateResponse("maintenance_dashboard.html", {"request": request, "user": current_user, "rows": rows, "counts": counts})


@router.get("/maintenance/rules", response_class=HTMLResponse)
def maintenance_rules_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rules = db.query(MaintenanceRule).options(joinedload(MaintenanceRule.equipment_type)).order_by(MaintenanceRule.id.desc()).all(); types = db.query(EquipmentType).order_by(EquipmentType.name).all()
    return templates.TemplateResponse("maintenance_rules.html", {"request": request, "user": current_user, "rules": rules, "types": types})


@router.post("/maintenance/rules/create")
def maintenance_rule_create(name: str = Form(...), equipment_type_id: int = Form(...), interval_km: str = Form(""), interval_hours: str = Form(""), interval_days: str = Form(""), warning_km: str = Form("500"), warning_days: str = Form("7"), description: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    def dec(v):
        try: return Decimal(v) if v else None
        except (InvalidOperation, ValueError): return None
    equipment_type = db.query(EquipmentType).filter(EquipmentType.id == equipment_type_id).first()
    if equipment_type is None: return RedirectResponse("/maintenance/rules", status_code=status.HTTP_303_SEE_OTHER)
    km = dec(interval_km); hours = dec(interval_hours); days = int(interval_days) if interval_days else None
    if equipment_type.measurement_unit == "km": hours = None
    elif equipment_type.measurement_unit == "hours": km = None
    rule = MaintenanceRule(name=name.strip(), equipment_type_id=equipment_type_id, interval_km=km, interval_hours=hours, interval_days=days, warning_km=dec(warning_km), warning_days=int(warning_days) if warning_days else None, description=description.strip() or None)
    db.add(rule); db.commit(); return RedirectResponse("/maintenance/rules", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/maintenance/records", response_class=HTMLResponse)
def maintenance_records_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    records = db.query(MaintenanceRecord).options(joinedload(MaintenanceRecord.equipment).joinedload(Equipment.equipment_type), joinedload(MaintenanceRecord.equipment).joinedload(Equipment.equipment_model), joinedload(MaintenanceRecord.rule)).order_by(desc(MaintenanceRecord.maintenance_date), desc(MaintenanceRecord.id)).all()
    equipment = db.query(Equipment).options(joinedload(Equipment.equipment_type), joinedload(Equipment.equipment_model)).order_by(Equipment.registration_number, Equipment.asset_code).all()
    rules = db.query(MaintenanceRule).filter(MaintenanceRule.is_active.is_(True)).order_by(MaintenanceRule.name).all()
    return templates.TemplateResponse("maintenance_records.html", {"request": request, "user": current_user, "records": records, "equipment": equipment, "rules": rules})


@router.post("/maintenance/records/create")
def maintenance_record_create(equipment_id: int = Form(...), rule_id: int = Form(...), maintenance_date: date = Form(...), meter_value: str = Form(""), work_order: str = Form(""), workshop: str = Form(""), description: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    records_url = "/maintenance/records"
    equipment = db.query(Equipment).options(joinedload(Equipment.equipment_type)).filter(Equipment.id == equipment_id).first()
    rule = db.query(MaintenanceRule).filter(MaintenanceRule.id == rule_id, MaintenanceRule.is_active.is_(True)).first()
    if equipment is None:
        return RedirectResponse(f"{records_url}?error=equipment", status_code=status.HTTP_303_SEE_OTHER)
    if rule is None:
        return RedirectResponse(f"{records_url}?error=rule", status_code=status.HTTP_303_SEE_OTHER)
    if rule.equipment_type_id != equipment.equipment_type_id:
        return RedirectResponse(f"{records_url}?error=rule_type", status_code=status.HTTP_303_SEE_OTHER)
    if maintenance_date > date.today():
        return RedirectResponse(f"{records_url}?error=future_date", status_code=status.HTTP_303_SEE_OTHER)

    unit = measurement_unit(equipment)
    meter = None
    if meter_value:
        try:
            meter = Decimal(meter_value)
        except (InvalidOperation, ValueError):
            return RedirectResponse(f"{records_url}?error=meter", status_code=status.HTTP_303_SEE_OTHER)
        if meter < 0:
            return RedirectResponse(f"{records_url}?error=meter", status_code=status.HTTP_303_SEE_OTHER)

    if (unit == "km" and rule.interval_km is not None) or (unit == "hours" and rule.interval_hours is not None):
        if meter is None:
            return RedirectResponse(f"{records_url}?error=meter_required", status_code=status.HTTP_303_SEE_OTHER)

    chronology = chronology_error(db, equipment_id, maintenance_date, meter)
    if chronology:
        return RedirectResponse(f"{records_url}?error=chronology", status_code=status.HTTP_303_SEE_OTHER)

    rec = MaintenanceRecord(
        equipment_id=equipment_id,
        rule_id=rule_id,
        maintenance_date=maintenance_date,
        meter_value=meter,
        work_order=work_order.strip() or None,
        workshop=workshop.strip() or None,
        description=description.strip() or None,
        status="completed",
        created_by_id=current_user.id if current_user else None,
    )
    db.add(rec)
    db.commit()
    return RedirectResponse(f"{records_url}?saved=1", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/maintenance/due", response_class=HTMLResponse)
def maintenance_due_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    equipment = db.query(Equipment).options(joinedload(Equipment.equipment_type), joinedload(Equipment.equipment_model)).all(); rules = db.query(MaintenanceRule).filter(MaintenanceRule.is_active.is_(True)).all(); readings = latest_readings(db); records = latest_records(db); due_rows = []
    for eq in equipment:
        current_value = current_meter_value(eq, readings.get(eq.id))
        for rule in rules:
            if rule.equipment_type_id != eq.equipment_type_id: continue
            rec = records.get((eq.id, rule.id)); state, css, remaining, meta = status_for(rule, eq, rec, current_value)
            if state in ("مستحقة الآن", "تقترب", "بلا سجل"):
                due_rows.append({"equipment": eq, "rule": rule, "record": rec, "current": current_value, "unit": measurement_unit(eq), "remaining": remaining, "remaining_days": meta.get("remaining_days"), "state": state, "css": css, "priority": priority_for(state, remaining, meta), "contradiction": contradiction_for(eq, rec, current_value, db)})
    due_rows.sort(key=lambda r: (r["priority"], r["remaining"] if r["remaining"] is not None else Decimal("999999999"), r["remaining_days"] if r["remaining_days"] is not None else 999999999)); return templates.TemplateResponse("maintenance_due.html", {"request": request, "user": current_user, "rows": due_rows})
