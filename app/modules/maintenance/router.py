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
from app.modules.equipment_types.models import EquipmentModel, EquipmentType
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


def chronology_error(db: Session, equipment_id: int, maintenance_date: date, meter: Decimal | None, exclude_id=None):
    if meter is None:
        return None
    records = db.query(MaintenanceRecord).filter(
        MaintenanceRecord.equipment_id == equipment_id,
        MaintenanceRecord.meter_value.is_not(None),
    ).order_by(MaintenanceRecord.maintenance_date, MaintenanceRecord.id).all()
    for row in records:
        if exclude_id is not None and row.id == exclude_id:
            continue
        if row.maintenance_date < maintenance_date and meter < Decimal(str(row.meter_value)):
            return "قراءة العداد أقل من قراءة سجل صيانة أقدم"
        if row.maintenance_date > maintenance_date and meter > Decimal(str(row.meter_value)):
            return "قراءة العداد أكبر من قراءة سجل صيانة أحدث"
    return None


def contradiction_for(equipment, record, current_value, db):
    if record is None or record.meter_value is None:
        return None
    error = chronology_error(db, equipment.id, record.maintenance_date, Decimal(str(record.meter_value)), exclude_id=record.id)
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


def effective_rules_for_equipment(db: Session, equipment, include_rule_id=None):
    """Return the rules that effectively apply to one equipment item."""
    rules = (
        db.query(MaintenanceRule)
        .options(joinedload(MaintenanceRule.equipment_type), joinedload(MaintenanceRule.equipment_model))
        .filter(MaintenanceRule.equipment_type_id == equipment.equipment_type_id)
        .order_by(MaintenanceRule.name, MaintenanceRule.id)
        .all()
    )
    base_rules = {rule.id: rule for rule in rules if rule.parent_rule_id is None}
    exceptions = {
        rule.parent_rule_id: rule
        for rule in rules
        if rule.parent_rule_id is not None
        and rule.equipment_model_id == equipment.equipment_model_id
    }
    result = []
    for base_id, base_rule in base_rules.items():
        exception = exceptions.get(base_id)
        if exception is not None:
            if exception.is_active or include_rule_id == exception.id:
                result.append(exception)
            elif include_rule_id == base_id:
                result.append(base_rule)
        elif base_rule.is_active or include_rule_id == base_id:
            result.append(base_rule)
    if include_rule_id is not None and not any(rule.id == include_rule_id for rule in result):
        historical = next((rule for rule in rules if rule.id == include_rule_id), None)
        if historical is not None:
            model_ok = historical.equipment_model_id is None or historical.equipment_model_id == equipment.equipment_model_id
            if model_ok:
                result.append(historical)
    return sorted(result, key=lambda rule: (rule.name, rule.id))


def get_effective_rule_for_equipment(db: Session, equipment, rule_id: int, include_historical: bool = False):
    rules = effective_rules_for_equipment(
        db,
        equipment,
        include_rule_id=rule_id if include_historical else None,
    )
    return next((rule for rule in rules if rule.id == rule_id), None)


@router.get("/maintenance", response_class=HTMLResponse)
def maintenance_dashboard_page(request: Request, current_user: User = Depends(get_current_user)):
    return templates.TemplateResponse("maintenance_home.html", {"request": request, "user": current_user})


@router.get("/maintenance/periodic", response_class=HTMLResponse)
def periodic_maintenance_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    equipment = db.query(Equipment).options(joinedload(Equipment.equipment_type), joinedload(Equipment.equipment_model)).order_by(Equipment.registration_number, Equipment.asset_code).all()
    readings = latest_readings(db); records = latest_records(db)
    rows = []; counts = {"total": 0, "danger": 0, "warning": 0, "success": 0, "neutral": 0}
    for eq in equipment:
        current_value = current_meter_value(eq, readings.get(eq.id))
        for rule in effective_rules_for_equipment(db, eq):
            rec = records.get((eq.id, rule.id)); state, css, remaining, meta = status_for(rule, eq, rec, current_value)
            counts["total"] += 1; counts[css] += 1
            rows.append({"equipment": eq, "rule": rule, "record": rec, "current": current_value, "unit": measurement_unit(eq), "next_meter": meta.get("next_meter"), "next_date": meta.get("next_date"), "remaining": remaining, "remaining_days": meta.get("remaining_days"), "state": state, "css": css, "priority": priority_for(state, remaining, meta), "contradiction": contradiction_for(eq, rec, current_value, db)})
    rows.sort(key=lambda r: (r["priority"], r["remaining"] if r["remaining"] is not None else Decimal("999999999"), r["remaining_days"] if r["remaining_days"] is not None else 999999999, r["equipment"].registration_number or r["equipment"].asset_code or ""))
    return templates.TemplateResponse("maintenance_dashboard.html", {"request": request, "user": current_user, "rows": rows, "counts": counts})


@router.get("/maintenance/rules", response_class=HTMLResponse)
def maintenance_rules_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rules = (
        db.query(MaintenanceRule)
        .options(
            joinedload(MaintenanceRule.equipment_type),
            joinedload(MaintenanceRule.equipment_model),
            joinedload(MaintenanceRule.parent_rule),
        )
        .order_by(MaintenanceRule.id.desc())
        .all()
    )
    types = db.query(EquipmentType).order_by(EquipmentType.name).all()
    models = db.query(EquipmentModel).options(joinedload(EquipmentModel.brand), joinedload(EquipmentModel.equipment_type)).order_by(EquipmentModel.name).all()
    base_rules = [r for r in rules if r.parent_rule_id is None]
    record_counts = {r.id: db.query(MaintenanceRecord.id).filter(MaintenanceRecord.rule_id == r.id).count() for r in rules}
    edit_rule = None
    edit_id = request.query_params.get("edit")
    if edit_id and edit_id.isdigit():
        edit_rule = db.query(MaintenanceRule).filter(MaintenanceRule.id == int(edit_id)).first()
    return templates.TemplateResponse(
        "maintenance_rules.html",
        {
            "request": request,
            "user": current_user,
            "rules": rules,
            "base_rules": base_rules,
            "types": types,
            "models": models,
            "record_counts": record_counts,
            "edit_rule": edit_rule,
        },
    )


@router.post("/maintenance/rules/{rule_id}/exceptions/create")
def maintenance_rule_exception_create(
    rule_id: int,
    equipment_model_id: int = Form(...),
    interval_km: str = Form(""),
    interval_hours: str = Form(""),
    interval_days: str = Form(""),
    warning_km: str = Form(""),
    warning_days: str = Form(""),
    description: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    parent = db.query(MaintenanceRule).filter(
        MaintenanceRule.id == rule_id,
        MaintenanceRule.parent_rule_id.is_(None),
    ).first()
    model = db.query(EquipmentModel).filter(EquipmentModel.id == equipment_model_id).first()
    if parent is None or model is None:
        return RedirectResponse("/maintenance/rules?error=not_found", status_code=status.HTTP_303_SEE_OTHER)
    if model.equipment_type_id != parent.equipment_type_id:
        return RedirectResponse("/maintenance/rules?error=model_type", status_code=status.HTTP_303_SEE_OTHER)
    if db.query(MaintenanceRule.id).filter(
        MaintenanceRule.parent_rule_id == parent.id,
        MaintenanceRule.equipment_model_id == model.id,
    ).first():
        return RedirectResponse("/maintenance/rules?error=exception_exists", status_code=status.HTTP_303_SEE_OTHER)

    def dec(v, fallback):
        try:
            return Decimal(v) if v else fallback
        except (InvalidOperation, ValueError):
            return fallback

    km = dec(interval_km, parent.interval_km)
    hours = dec(interval_hours, parent.interval_hours)
    days = int(interval_days) if interval_days else parent.interval_days
    warning_km_value = dec(warning_km, parent.warning_km)
    warning_days_value = int(warning_days) if warning_days else parent.warning_days
    if parent.equipment_type.measurement_unit == "km":
        hours = None
    elif parent.equipment_type.measurement_unit == "hours":
        km = None
    if not (km or hours or days):
        return RedirectResponse("/maintenance/rules?error=invalid", status_code=status.HTTP_303_SEE_OTHER)

    exception = MaintenanceRule(
        name=parent.name,
        equipment_type_id=parent.equipment_type_id,
        equipment_model_id=model.id,
        parent_rule_id=parent.id,
        interval_km=km,
        interval_hours=hours,
        interval_days=days,
        warning_km=warning_km_value,
        warning_days=warning_days_value,
        is_active=True,
        description=description.strip() or parent.description,
    )
    db.add(exception)
    db.commit()
    return RedirectResponse("/maintenance/rules?saved=exception", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/maintenance/rules/{rule_id}/exceptions/update")
def maintenance_rule_exception_update(
    rule_id: int,
    interval_km: str = Form(""),
    interval_hours: str = Form(""),
    interval_days: str = Form(""),
    warning_km: str = Form(""),
    warning_days: str = Form(""),
    description: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    exception = (
        db.query(MaintenanceRule)
        .options(joinedload(MaintenanceRule.parent_rule), joinedload(MaintenanceRule.equipment_model))
        .filter(MaintenanceRule.id == rule_id, MaintenanceRule.parent_rule_id.is_not(None))
        .first()
    )
    if exception is None:
        return RedirectResponse("/maintenance/rules?error=not_found", status_code=status.HTTP_303_SEE_OTHER)
    parent = exception.parent_rule
    unit = parent.equipment_type.measurement_unit

    def dec(v, fallback):
        try:
            return Decimal(v) if v else fallback
        except (InvalidOperation, ValueError):
            return fallback

    km = dec(interval_km, parent.interval_km)
    hours = dec(interval_hours, parent.interval_hours)
    days = int(interval_days) if interval_days else parent.interval_days
    warning_km_value = dec(warning_km, parent.warning_km)
    warning_days_value = int(warning_days) if warning_days else parent.warning_days
    if unit == "km":
        hours = None
    elif unit == "hours":
        km = None
    if not (km or hours or days):
        return RedirectResponse(f"/maintenance/rules?edit={rule_id}&error=invalid#editException", status_code=status.HTTP_303_SEE_OTHER)

    exception.interval_km = km
    exception.interval_hours = hours
    exception.interval_days = days
    exception.warning_km = warning_km_value
    exception.warning_days = warning_days_value
    exception.description = description.strip() or parent.description
    db.commit()
    return RedirectResponse("/maintenance/rules?saved=exception_updated", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/maintenance/rules/create")
def maintenance_rule_create(name: str = Form(...), equipment_type_id: int = Form(...), interval_km: str = Form(""), interval_hours: str = Form(""), interval_days: str = Form(""), warning_km: str = Form("500"), warning_days: str = Form("7"), description: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    def dec(v):
        try: return Decimal(v) if v else None
        except (InvalidOperation, ValueError): return None
    equipment_type = db.query(EquipmentType).filter(EquipmentType.id == equipment_type_id).first()
    if equipment_type is None: return RedirectResponse("/maintenance/rules?error=equipment_type", status_code=status.HTTP_303_SEE_OTHER)
    km = dec(interval_km); hours = dec(interval_hours); days = int(interval_days) if interval_days else None
    if equipment_type.measurement_unit == "km": hours = None
    elif equipment_type.measurement_unit == "hours": km = None
    rule = MaintenanceRule(name=name.strip(), equipment_type_id=equipment_type_id, interval_km=km, interval_hours=hours, interval_days=days, warning_km=dec(warning_km), warning_days=int(warning_days) if warning_days else None, description=description.strip() or None)
    db.add(rule); db.commit(); return RedirectResponse("/maintenance/rules?saved=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/maintenance/rules/{rule_id}/update")
def maintenance_rule_update(rule_id: int, name: str = Form(...), equipment_type_id: int = Form(...), interval_km: str = Form(""), interval_hours: str = Form(""), interval_days: str = Form(""), warning_km: str = Form("500"), warning_days: str = Form("7"), description: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rule = db.query(MaintenanceRule).filter(MaintenanceRule.id == rule_id).first()
    equipment_type = db.query(EquipmentType).filter(EquipmentType.id == equipment_type_id).first()
    if rule is not None and rule.parent_rule_id is not None:
        return RedirectResponse(f"/maintenance/rules?edit={rule_id}&error=use_exception_form#editException", status_code=status.HTTP_303_SEE_OTHER)
    if rule is None or equipment_type is None:
        return RedirectResponse("/maintenance/rules?error=not_found", status_code=status.HTTP_303_SEE_OTHER)
    def dec(v):
        try: return Decimal(v) if v else None
        except (InvalidOperation, ValueError): return None
    km = dec(interval_km); hours = dec(interval_hours); days = int(interval_days) if interval_days else None
    if equipment_type.measurement_unit == "km": hours = None
    elif equipment_type.measurement_unit == "hours": km = None
    if not name.strip() or not (km or hours or days):
        return RedirectResponse(f"/maintenance/rules?edit={rule_id}&error=invalid", status_code=status.HTTP_303_SEE_OTHER)
    rule.name = name.strip(); rule.equipment_type_id = equipment_type_id; rule.interval_km = km; rule.interval_hours = hours; rule.interval_days = days; rule.warning_km = dec(warning_km); rule.warning_days = int(warning_days) if warning_days else None; rule.description = description.strip() or None
    db.commit()
    return RedirectResponse("/maintenance/rules?saved=updated", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/maintenance/rules/{rule_id}/toggle")
def maintenance_rule_toggle(rule_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rule = db.query(MaintenanceRule).filter(MaintenanceRule.id == rule_id).first()
    if rule is None: return RedirectResponse("/maintenance/rules?error=not_found", status_code=status.HTTP_303_SEE_OTHER)
    rule.is_active = not rule.is_active
    db.commit()
    return RedirectResponse("/maintenance/rules?changed=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/maintenance/rules/{rule_id}/delete")
def maintenance_rule_delete(rule_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rule = db.query(MaintenanceRule).filter(MaintenanceRule.id == rule_id).first()
    if rule is None: return RedirectResponse("/maintenance/rules?error=not_found", status_code=status.HTTP_303_SEE_OTHER)
    used = db.query(MaintenanceRecord.id).filter(MaintenanceRecord.rule_id == rule_id).first()
    if used:
        rule.is_active = False
        db.commit()
        return RedirectResponse("/maintenance/rules?changed=deactivated", status_code=status.HTTP_303_SEE_OTHER)
    db.delete(rule); db.commit()
    return RedirectResponse("/maintenance/rules?changed=deleted", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/maintenance/records", response_class=HTMLResponse)
def maintenance_records_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    records = db.query(MaintenanceRecord).options(joinedload(MaintenanceRecord.equipment).joinedload(Equipment.equipment_type), joinedload(MaintenanceRecord.equipment).joinedload(Equipment.equipment_model), joinedload(MaintenanceRecord.rule)).order_by(desc(MaintenanceRecord.maintenance_date), desc(MaintenanceRecord.id)).all()
    equipment = db.query(Equipment).options(joinedload(Equipment.equipment_type), joinedload(Equipment.equipment_model)).order_by(Equipment.registration_number, Equipment.asset_code).all()
    rules = db.query(MaintenanceRule).filter(MaintenanceRule.is_active.is_(True)).order_by(MaintenanceRule.name, MaintenanceRule.id).all()
    edit_record = None
    edit_id = request.query_params.get("edit")
    if edit_id and edit_id.isdigit(): edit_record = db.query(MaintenanceRecord).filter(MaintenanceRecord.id == int(edit_id)).first()
    if edit_record and edit_record.rule_id not in {rule.id for rule in rules}:
        historical_rule = db.query(MaintenanceRule).filter(MaintenanceRule.id == edit_record.rule_id).first()
        if historical_rule is not None:
            rules.append(historical_rule)
    effective_rule_equipment_ids = {}
    for eq in equipment:
        for rule in effective_rules_for_equipment(db, eq):
            effective_rule_equipment_ids.setdefault(rule.id, set()).add(eq.id)
    effective_rule_equipment_ids = {
        rule_id: ",".join(str(equipment_id) for equipment_id in sorted(equipment_ids))
        for rule_id, equipment_ids in effective_rule_equipment_ids.items()
    }
    return templates.TemplateResponse(
        "maintenance_records.html",
        {
            "request": request,
            "user": current_user,
            "records": records,
            "equipment": equipment,
            "rules": rules,
            "effective_rule_equipment_ids": effective_rule_equipment_ids,
            "edit_record": edit_record,
        },
    )


@router.post("/maintenance/records/create")
def maintenance_record_create(equipment_id: int = Form(...), rule_id: int = Form(...), maintenance_date: date = Form(...), meter_value: str = Form(""), work_order: str = Form(""), workshop: str = Form(""), description: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    records_url = "/maintenance/records"
    equipment = db.query(Equipment).options(joinedload(Equipment.equipment_type)).filter(Equipment.id == equipment_id).first()
    rule = get_effective_rule_for_equipment(db, equipment, rule_id)
    if equipment is None: return RedirectResponse(f"{records_url}?error=equipment", status_code=status.HTTP_303_SEE_OTHER)
    if rule is None: return RedirectResponse(f"{records_url}?error=rule_type", status_code=status.HTTP_303_SEE_OTHER)
    if maintenance_date > date.today(): return RedirectResponse(f"{records_url}?error=future_date", status_code=status.HTTP_303_SEE_OTHER)
    unit = measurement_unit(equipment); meter = None
    if meter_value:
        try: meter = Decimal(meter_value)
        except (InvalidOperation, ValueError): return RedirectResponse(f"{records_url}?error=meter", status_code=status.HTTP_303_SEE_OTHER)
        if meter < 0: return RedirectResponse(f"{records_url}?error=meter", status_code=status.HTTP_303_SEE_OTHER)
    if (unit == "km" and rule.interval_km is not None) or (unit == "hours" and rule.interval_hours is not None):
        if meter is None: return RedirectResponse(f"{records_url}?error=meter_required", status_code=status.HTTP_303_SEE_OTHER)
    chronology = chronology_error(db, equipment_id, maintenance_date, meter)
    if chronology: return RedirectResponse(f"{records_url}?error=chronology", status_code=status.HTTP_303_SEE_OTHER)
    rec = MaintenanceRecord(equipment_id=equipment_id, rule_id=rule_id, maintenance_date=maintenance_date, meter_value=meter, work_order=work_order.strip() or None, workshop=workshop.strip() or None, description=description.strip() or None, status="completed", created_by_id=current_user.id if current_user else None)
    db.add(rec); db.commit()
    return RedirectResponse(f"{records_url}?saved=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/maintenance/records/{record_id}/update")
def maintenance_record_update(record_id: int, equipment_id: int = Form(...), rule_id: int = Form(...), maintenance_date: date = Form(...), meter_value: str = Form(""), work_order: str = Form(""), workshop: str = Form(""), description: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    records_url = "/maintenance/records"
    rec = db.query(MaintenanceRecord).filter(MaintenanceRecord.id == record_id).first()
    equipment = db.query(Equipment).options(joinedload(Equipment.equipment_type)).filter(Equipment.id == equipment_id).first()
    rule = get_effective_rule_for_equipment(db, equipment, rule_id, include_historical=True)
    if rec is None or equipment is None or rule is None: return RedirectResponse(f"{records_url}?error=not_found", status_code=status.HTTP_303_SEE_OTHER)
    if maintenance_date > date.today(): return RedirectResponse(f"{records_url}?error=future_date", status_code=status.HTTP_303_SEE_OTHER)
    meter = None
    if meter_value:
        try: meter = Decimal(meter_value)
        except (InvalidOperation, ValueError): return RedirectResponse(f"{records_url}?error=meter", status_code=status.HTTP_303_SEE_OTHER)
        if meter < 0: return RedirectResponse(f"{records_url}?error=meter", status_code=status.HTTP_303_SEE_OTHER)
    unit = measurement_unit(equipment)
    if (unit == "km" and rule.interval_km is not None) or (unit == "hours" and rule.interval_hours is not None):
        if meter is None: return RedirectResponse(f"{records_url}?error=meter_required", status_code=status.HTTP_303_SEE_OTHER)
    chronology = chronology_error(db, equipment_id, maintenance_date, meter, exclude_id=record_id)
    if chronology: return RedirectResponse(f"{records_url}?error=chronology", status_code=status.HTTP_303_SEE_OTHER)
    rec.equipment_id = equipment_id; rec.rule_id = rule_id; rec.maintenance_date = maintenance_date; rec.meter_value = meter; rec.work_order = work_order.strip() or None; rec.workshop = workshop.strip() or None; rec.description = description.strip() or None
    db.commit()
    return RedirectResponse(f"{records_url}?saved=updated", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/maintenance/records/{record_id}/delete")
def maintenance_record_delete(record_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rec = db.query(MaintenanceRecord).filter(MaintenanceRecord.id == record_id).first()
    if rec is None: return RedirectResponse("/maintenance/records?error=not_found", status_code=status.HTTP_303_SEE_OTHER)
    db.delete(rec); db.commit()
    return RedirectResponse("/maintenance/records?changed=deleted", status_code=status.HTTP_303_SEE_OTHER)


@router.get("/maintenance/due", response_class=HTMLResponse)
def maintenance_due_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    equipment = db.query(Equipment).options(joinedload(Equipment.equipment_type), joinedload(Equipment.equipment_model)).all(); readings = latest_readings(db); records = latest_records(db); due_rows = []
    for eq in equipment:
        current_value = current_meter_value(eq, readings.get(eq.id))
        for rule in effective_rules_for_equipment(db, eq):
            rec = records.get((eq.id, rule.id)); state, css, remaining, meta = status_for(rule, eq, rec, current_value)
            if state in ("مستحقة الآن", "تقترب", "بلا سجل"):
                due_rows.append({"equipment": eq, "rule": rule, "record": rec, "current": current_value, "unit": measurement_unit(eq), "remaining": remaining, "remaining_days": meta.get("remaining_days"), "state": state, "css": css, "priority": priority_for(state, remaining, meta), "contradiction": contradiction_for(eq, rec, current_value, db)})
    due_rows.sort(key=lambda r: (r["priority"], r["remaining"] if r["remaining"] is not None else Decimal("999999999"), r["remaining_days"] if r["remaining_days"] is not None else 999999999)); return templates.TemplateResponse("maintenance_due.html", {"request": request, "user": current_user, "rows": due_rows})