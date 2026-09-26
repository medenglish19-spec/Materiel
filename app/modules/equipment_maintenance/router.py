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
from app.modules.maintenance.models import MaintenanceOperation, MaintenanceRecord
from app.modules.maintenance.services import chronology_error, effective_operations_for_equipment, measurement_unit
from app.modules.users.models import User

router = APIRouter()
templates = get_module_templates("app/modules/equipment_maintenance/templates")

def get_equipment(db: Session, equipment_id: int):
    return db.query(Equipment).options(
        joinedload(Equipment.equipment_type), joinedload(Equipment.equipment_model)
    ).filter(Equipment.id == equipment_id).first()

def get_operations(db: Session, equipment):
    return effective_operations_for_equipment(db, equipment, include_standalone=True)

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

def validate_operation(db: Session, equipment, operation_id: int):
    operation = db.query(MaintenanceOperation).filter(
        MaintenanceOperation.id == operation_id,
        MaintenanceOperation.is_active.is_(True),
    ).first()
    if operation is None:
        raise HTTPException(status_code=400, detail="عملية الصيانة المحددة غير موجودة أو غير مفعلة.")
    if operation.id not in {item.id for item in get_operations(db, equipment)}:
        raise HTTPException(status_code=400, detail="عملية الصيانة المختارة لا تنطبق على طراز هذا العتاد.")
    return operation

def validate_meter_and_date(db, equipment, operation, maintenance_date, meter_value, exclude_id=None):
    if maintenance_date > date.today():
        raise HTTPException(status_code=400, detail="لا يمكن تسجيل صيانة بتاريخ مستقبلي.")
    meter = parse_meter(meter_value)
    unit = measurement_unit(equipment)
    interval = operation.interval_km if unit == "km" else operation.interval_hours if unit == "hours" else None
    if interval is not None and meter is None:
        raise HTTPException(status_code=400, detail="يجب إدخال العداد عند الصيانة لأن هذه العملية تعتمد على العداد.")
    chronology = chronology_error(db, equipment.id, maintenance_date, meter, exclude_id=exclude_id)
    if chronology:
        raise HTTPException(status_code=400, detail=chronology)
    return meter

@router.get("/equipment/{equipment_id}/maintenance", response_class=HTMLResponse)
def equipment_maintenance_page(equipment_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = get_equipment(db, equipment_id)
    if not item:
        raise HTTPException(status_code=404, detail="العتاد غير موجود")
    records = db.query(MaintenanceRecord).options(
        joinedload(MaintenanceRecord.operation), joinedload(MaintenanceRecord.plan)
    ).filter(MaintenanceRecord.equipment_id == equipment_id).order_by(
        desc(MaintenanceRecord.maintenance_date), desc(MaintenanceRecord.id)
    ).all()
    edit_record = None
    edit_id = request.query_params.get("edit")
    if edit_id and edit_id.isdigit():
        edit_record = db.query(MaintenanceRecord).options(
            joinedload(MaintenanceRecord.operation), joinedload(MaintenanceRecord.plan)
        ).filter(MaintenanceRecord.id == int(edit_id), MaintenanceRecord.equipment_id == equipment_id).first()
    return templates.TemplateResponse("equipment_maintenance.html", {
        "request": request, "user": current_user, "item": item, "records": records,
        "operations": get_operations(db, item), "edit_record": edit_record,
    })

@router.post("/equipment/{equipment_id}/maintenance/create")
def equipment_maintenance_create(equipment_id: int, operation_id: int = Form(...), maintenance_date: date = Form(...),
                                  meter_value: str = Form(""), work_order: str = Form(""), workshop: str = Form(""),
                                  description: str = Form(""), db: Session = Depends(get_db),
                                  current_user: User = Depends(get_current_user)):
    item = get_equipment(db, equipment_id)
    if not item:
        raise HTTPException(status_code=404, detail="العتاد غير موجود")
    operation = validate_operation(db, item, operation_id)
    meter = validate_meter_and_date(db, item, operation, maintenance_date, meter_value)
    record = MaintenanceRecord(equipment_id=equipment_id, operation_id=operation.id,
        maintenance_date=maintenance_date, reported_date=maintenance_date, meter_value=meter,
        work_order=work_order.strip() or None, workshop=workshop.strip() or None,
        description=description.strip() or None, status="completed", created_by_id=current_user.id)
    try:
        db.add(record); db.commit()
    except ValueError as exc:
        db.rollback(); raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url=f"/equipment/{equipment_id}/maintenance?saved=1", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/equipment/{equipment_id}/maintenance/{record_id}/update")
def equipment_maintenance_update(equipment_id: int, record_id: int, operation_id: int = Form(...), maintenance_date: date = Form(...),
                                 meter_value: str = Form(""), work_order: str = Form(""), workshop: str = Form(""),
                                 description: str = Form(""), db: Session = Depends(get_db),
                                 current_user: User = Depends(get_current_user)):
    item = get_equipment(db, equipment_id)
    record = db.query(MaintenanceRecord).filter(MaintenanceRecord.id == record_id, MaintenanceRecord.equipment_id == equipment_id).first()
    if not item or not record:
        raise HTTPException(status_code=404, detail="سجل الصيانة غير موجود لهذا العتاد.")
    operation = validate_operation(db, item, operation_id)
    meter = validate_meter_and_date(db, item, operation, maintenance_date, meter_value, exclude_id=record_id)
    record.operation_id = operation.id; record.maintenance_date = maintenance_date; record.reported_date = maintenance_date
    record.meter_value = meter; record.work_order = work_order.strip() or None
    record.workshop = workshop.strip() or None; record.description = description.strip() or None
    try:
        db.commit()
    except ValueError as exc:
        db.rollback(); raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url=f"/equipment/{equipment_id}/maintenance?saved=updated", status_code=status.HTTP_303_SEE_OTHER)

@router.post("/equipment/{equipment_id}/maintenance/{record_id}/delete")
def equipment_maintenance_delete(equipment_id: int, record_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    record = db.query(MaintenanceRecord).filter(MaintenanceRecord.id == record_id, MaintenanceRecord.equipment_id == equipment_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="سجل الصيانة غير موجود لهذا العتاد.")
    db.delete(record); db.commit()
    return RedirectResponse(url=f"/equipment/{equipment_id}/maintenance?changed=deleted", status_code=status.HTTP_303_SEE_OTHER)
