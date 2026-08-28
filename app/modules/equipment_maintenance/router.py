from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import desc
from sqlalchemy.orm import Session, joinedload

from app.core.dependencies import get_current_user
from app.core.templating import get_module_templates
from app.database.session import get_db
from app.modules.equipment.models import Equipment
from app.modules.maintenance.models import MaintenanceRecord, MaintenanceRule
from app.modules.maintenance.router import (
    chronology_error,
    effective_rules_for_equipment,
    get_effective_rule_for_equipment,
    measurement_unit,
)
from app.modules.users.models import User

router = APIRouter()
templates = get_module_templates("app/modules/equipment_maintenance/templates")


def get_equipment(db: Session, equipment_id: int):
    return (
        db.query(Equipment)
        .options(joinedload(Equipment.equipment_type), joinedload(Equipment.equipment_model))
        .filter(Equipment.id == equipment_id)
        .first()
    )


def get_rules(db: Session, equipment, include_rule_id=None):
    return effective_rules_for_equipment(
        db,
        equipment,
        include_rule_id=include_rule_id,
    )


def parse_meter(value: str):
    if not value or not value.strip():
        return None
    try:
        meter = Decimal(value)
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=400, detail="قيمة العداد غير صحيحة.")
    if meter < 0:
        raise HTTPException(status_code=400, detail="قيمة العداد لا يمكن أن تكون سالبة.")
    return meter


@router.get("/equipment/{equipment_id}/maintenance", response_class=HTMLResponse)
def equipment_maintenance_page(
    equipment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = get_equipment(db, equipment_id)
    if not item:
        raise HTTPException(status_code=404, detail="العتاد غير موجود")

    records = (
        db.query(MaintenanceRecord)
        .options(joinedload(MaintenanceRecord.rule))
        .filter(MaintenanceRecord.equipment_id == equipment_id)
        .order_by(desc(MaintenanceRecord.maintenance_date), desc(MaintenanceRecord.id))
        .all()
    )
    edit_record = None
    edit_id = request.query_params.get("edit")
    if edit_id and edit_id.isdigit():
        edit_record = (
            db.query(MaintenanceRecord)
            .options(joinedload(MaintenanceRecord.rule))
            .filter(
                MaintenanceRecord.id == int(edit_id),
                MaintenanceRecord.equipment_id == equipment_id,
            )
            .first()
        )
    rules = get_rules(db, item, edit_record.rule_id if edit_record else None)
    return templates.TemplateResponse(
        "equipment_maintenance.html",
        {
            "request": request,
            "user": current_user,
            "item": item,
            "records": records,
            "rules": rules,
            "edit_record": edit_record,
        },
    )


@router.post("/equipment/{equipment_id}/maintenance/create")
def equipment_maintenance_create(
    equipment_id: int,
    rule_id: int = Form(...),
    maintenance_date: date = Form(...),
    meter_value: str = Form(""),
    work_order: str = Form(""),
    workshop: str = Form(""),
    description: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = get_equipment(db, equipment_id)
    if not item:
        raise HTTPException(status_code=404, detail="العتاد غير موجود")
    rule = get_effective_rule_for_equipment(db, item, rule_id)
    if not rule:
        raise HTTPException(status_code=400, detail="الصيانة الدورية المختارة لا تتبع نوع عتاد هذا العتاد.")
    if maintenance_date > date.today():
        raise HTTPException(status_code=400, detail="لا يمكن تسجيل صيانة بتاريخ مستقبلي.")

    meter = parse_meter(meter_value)
    unit = measurement_unit(item)
    if ((unit == "km" and rule.interval_km is not None) or (unit == "hours" and rule.interval_hours is not None)) and meter is None:
        raise HTTPException(status_code=400, detail="يجب إدخال العداد عند الصيانة لأن هذا الشرط يعتمد على العداد.")
    chronology = chronology_error(db, equipment_id, maintenance_date, meter)
    if chronology:
        raise HTTPException(status_code=400, detail=chronology)

    record = MaintenanceRecord(
        equipment_id=equipment_id,
        rule_id=rule_id,
        maintenance_date=maintenance_date,
        meter_value=meter,
        work_order=work_order.strip() or None,
        workshop=workshop.strip() or None,
        description=description.strip() or None,
        status="completed",
        created_by_id=current_user.id,
    )
    try:
        db.add(record)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url=f"/equipment/{equipment_id}/maintenance?saved=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/equipment/{equipment_id}/maintenance/{record_id}/update")
def equipment_maintenance_update(
    equipment_id: int,
    record_id: int,
    rule_id: int = Form(...),
    maintenance_date: date = Form(...),
    meter_value: str = Form(""),
    work_order: str = Form(""),
    workshop: str = Form(""),
    description: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = get_equipment(db, equipment_id)
    record = (
        db.query(MaintenanceRecord)
        .filter(MaintenanceRecord.id == record_id, MaintenanceRecord.equipment_id == equipment_id)
        .first()
    )
    if not item or not record:
        raise HTTPException(status_code=404, detail="سجل الصيانة غير موجود لهذا العتاد.")
    rule = get_effective_rule_for_equipment(db, item, rule_id, include_historical=True)
    if not rule:
        raise HTTPException(status_code=400, detail="الصيانة الدورية المختارة لا تتبع نوع عتاد هذا العتاد.")
    if maintenance_date > date.today():
        raise HTTPException(status_code=400, detail="لا يمكن تسجيل صيانة بتاريخ مستقبلي.")

    meter = parse_meter(meter_value)
    unit = measurement_unit(item)
    if ((unit == "km" and rule.interval_km is not None) or (unit == "hours" and rule.interval_hours is not None)) and meter is None:
        raise HTTPException(status_code=400, detail="يجب إدخال العداد عند الصيانة لأن هذا الشرط يعتمد على العداد.")
    chronology = chronology_error(db, equipment_id, maintenance_date, meter, exclude_id=record_id)
    if chronology:
        raise HTTPException(status_code=400, detail=chronology)

    record.rule_id = rule_id
    record.maintenance_date = maintenance_date
    record.meter_value = meter
    record.work_order = work_order.strip() or None
    record.workshop = workshop.strip() or None
    record.description = description.strip() or None
    try:
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url=f"/equipment/{equipment_id}/maintenance?saved=updated", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/equipment/{equipment_id}/maintenance/{record_id}/delete")
def equipment_maintenance_delete(
    equipment_id: int,
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    record = db.query(MaintenanceRecord).filter(
        MaintenanceRecord.id == record_id,
        MaintenanceRecord.equipment_id == equipment_id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="سجل الصيانة غير موجود لهذا العتاد.")
    db.delete(record)
    db.commit()
    return RedirectResponse(url=f"/equipment/{equipment_id}/maintenance?changed=deleted", status_code=status.HTTP_303_SEE_OTHER)
