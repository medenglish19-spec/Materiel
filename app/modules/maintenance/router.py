from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import desc, delete
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.core.permissions import Role, require_min_role
from app.core.templating import get_module_templates
from app.database.session import get_db
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentModel, EquipmentType
from app.modules.maintenance.models import (MaintenanceOperation, MaintenanceOperationGroup, MaintenancePlan, MaintenancePlanOperation, MaintenanceRecord, maintenance_operation_models)
from app.modules.maintenance.schemas import (MaintenanceOperationBulkDelete, MaintenanceOperationCreate, MaintenanceOperationGroupCreate, MaintenanceOperationGroupOut, MaintenanceOperationGroupUpdate, MaintenanceOperationOut, MaintenanceOperationUpdate, MaintenancePlanBulkDelete, MaintenancePlanCreate, MaintenancePlanOperationCreate, MaintenancePlanOperationOut, MaintenancePlanOut, MaintenancePlanUpdate, MaintenanceRecordBulkDelete, MaintenanceRecordCreate, MaintenanceRecordOut, MaintenancePlanExecutionCreate)
from app.modules.maintenance.services import (
    maintenance_record_has_execution_data,
    maintenance_record_delete_reason,
    chronology_error,
    contradiction_for,
    current_meter_value,
    effective_operations_for_equipment,
    latest_readings,
    latest_records,
    measurement_unit,
    priority_for,
    status_for,
    plan_status_for,
    effective_plans_for_equipment,
    latest_plan_records,
    validate_operation_applicable_to_equipment,
    operations_payload,
    operation_tasks_for_model,
    plan_condition,
)
from app.modules.users.models import User
from app.modules.faults_repairs.models import Technician
from app.modules.faults_repairs.services import list_technicians

router = APIRouter()
templates = get_module_templates("app/modules/maintenance/templates")


def _sync_operation_model_conditions(db: Session, operation, submitted: list) -> None:
    """Write the submitted per-model conditions of one operation.

    Each relation row is written on its own, so changing one model's condition
    cannot alter another model's row. Models absent from the payload lose their
    relation row; models present in both keep their existing row.
    """
    from app.modules.maintenance.schemas import MaintenanceOperationModelConditionIn
    by_model = {}
    for index, item in enumerate(submitted):
        data = item.model_dump() if hasattr(item, "model_dump") else dict(item)
        model_id = data.pop("model_id")
        if model_id in by_model:
            raise HTTPException(status_code=400, detail="نموذج مكرر أكثر من مرة في نفس العملية.")
        if db.get(EquipmentModel, model_id) is None:
            raise HTTPException(status_code=404, detail="طراز العتاد غير موجود.")
        by_model[model_id] = (index, data)

    existing = {
        row.equipment_model_id: row
        for row in db.execute(
            maintenance_operation_models.select().where(
                maintenance_operation_models.c.operation_id == operation.id
            )
        ).all()
    }

    for model_id in list(existing):
        if model_id not in by_model:
            db.execute(
                delete(maintenance_operation_models).where(
                    maintenance_operation_models.c.operation_id == operation.id,
                    maintenance_operation_models.c.equipment_model_id == model_id,
                )
            )

    for model_id, (_, data) in by_model.items():
        row = existing.get(model_id)
        if row is None:
            db.execute(
                maintenance_operation_models.insert().values(
                    operation_id=operation.id, equipment_model_id=model_id, **data
                )
            )
        else:
            db.execute(
                maintenance_operation_models.update()
                .where(
                    maintenance_operation_models.c.operation_id == operation.id,
                    maintenance_operation_models.c.equipment_model_id == model_id,
                )
                .values(**data)
            )

    db.expire(operation, ["equipment_models"])


def _delete_plan(db: Session, plan: MaintenancePlan) -> None:
    """Delete a plan only when it has no records with actual execution data."""
    plan_records = db.query(MaintenanceRecord).filter(
        MaintenanceRecord.plan_id == plan.id
    ).all()
    if any(maintenance_record_has_execution_data(record) for record in plan_records):
        raise ValueError("لا يمكن حذف الخطة لارتباطها بسجلات تنفيذ تاريخية.")
    db.query(MaintenancePlanOperation).filter(
        MaintenancePlanOperation.plan_id == plan.id
    ).delete(synchronize_session=False)
    db.delete(plan)


@router.get("/maintenance", response_class=HTMLResponse)
def maintenance_dashboard_page(request: Request, current_user: User = Depends(get_current_user)):
    return templates.TemplateResponse(request=request, name="maintenance_home.html", context={"request": request, "user": current_user})


@router.get("/maintenance/periodic", response_class=HTMLResponse)
def periodic_maintenance_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    equipment = db.query(Equipment).options(joinedload(Equipment.equipment_type), joinedload(Equipment.equipment_model)).order_by(Equipment.registration_number, Equipment.asset_code).all()
    readings = latest_readings(db); records = latest_records(db)
    rows = []; counts = {"total": 0, "danger": 0, "warning": 0, "success": 0, "neutral": 0}
    tasks_by_model = {}
    model_ids = {eq.equipment_model_id for eq in equipment if eq.equipment_model_id is not None}
    approved_model_ids = {
        model_id for (model_id,) in db.query(MaintenancePlan.equipment_model_id).filter(
            MaintenancePlan.equipment_model_id.in_(model_ids or {-1}),
            MaintenancePlan.is_active.is_(True),
            MaintenancePlan.is_approved.is_(True),
        ).distinct().all()
    }
    unapproved_models = sorted({
        eq.equipment_model.name
        for eq in equipment
        if eq.equipment_model_id is not None
        and eq.equipment_model is not None
        and eq.equipment_model_id not in approved_model_ids
    })
    for eq in equipment:
        current_value = current_meter_value(eq, readings.get(eq.id))
        model_id = eq.equipment_model_id
        if model_id is not None and model_id not in tasks_by_model:
            tasks_by_model[model_id] = operation_tasks_for_model(db, model_id)
        for task in tasks_by_model.get(model_id, []):
            operation = task.operation
            rec = records.get((eq.id, operation.id))
            # العمليات التابعة للخطة تُقاس بشرط خطتها؛ والمستقلة بشرط طرازها.
            state, css, remaining, meta = status_for(operation, eq, rec, current_value, condition=task.condition)
            counts["total"] += 1; counts[css] += 1
            rows.append({"equipment": eq, "operation": operation, "record": rec, "current": current_value, "unit": measurement_unit(eq), "next_meter": meta.get("next_meter"), "next_date": meta.get("next_date"), "remaining": remaining, "remaining_days": meta.get("remaining_days"), "state": state, "css": css, "priority": priority_for(state, remaining, meta), "contradiction": contradiction_for(eq, rec, current_value, db), "plan": task.plan})
    rows.sort(key=lambda r: (r["priority"], r["remaining"] if r["remaining"] is not None else Decimal("999999999"), r["remaining_days"] if r["remaining_days"] is not None else 999999999, r["equipment"].registration_number or r["equipment"].asset_code or ""))
    return templates.TemplateResponse(request=request, name="maintenance_dashboard.html", context={"request": request, "user": current_user, "rows": rows, "counts": counts, "unapproved_models": unapproved_models})


@router.get("/maintenance/plans", response_class=HTMLResponse)
def maintenance_plans_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    models = db.query(EquipmentModel).options(
        joinedload(EquipmentModel.brand),
        joinedload(EquipmentModel.equipment_type),
    ).order_by(EquipmentModel.name).all()
    model_options = [{"id": model.id, "name": model.name} for model in models]
    # Build operation conditions for the template as a dict with composite keys
    operations = db.query(MaintenanceOperation).order_by(MaintenanceOperation.name, MaintenanceOperation.id).all()
    operation_conditions_list = operations_payload(db, operations)
    # Transform to dict with keys like "operation_id:model_id"
    operation_conditions = {}
    for op in operation_conditions_list:
        for mc in op.get("model_conditions", []):
            key = f"{op['id']}:{mc['model_id']}"
            operation_conditions[key] = mc
    return templates.TemplateResponse(
        request=request, name="maintenance_plans.html", context={"request": request, "user": current_user, "models": model_options, "operation_conditions": operation_conditions},
    )

@router.get("/maintenance/rules", response_class=HTMLResponse)
def maintenance_rules_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    models = db.query(EquipmentModel).options(
        joinedload(EquipmentModel.brand),
        joinedload(EquipmentModel.equipment_type),
    ).order_by(EquipmentModel.name).all()
    return templates.TemplateResponse(
        request=request, name="maintenance_rules_model_only.html", context={"request": request, "user": current_user, "models": models},
    )

@router.get("/maintenance/records", response_class=HTMLResponse)
def maintenance_records_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    can_manage_records = settings.DEV_DISABLE_AUTH or current_user.role in {
        Role.ADMIN.value,
        Role.FLEET_MANAGER.value,
    }
    records = db.query(MaintenanceRecord).options(
        joinedload(MaintenanceRecord.equipment).joinedload(Equipment.equipment_type),
        joinedload(MaintenanceRecord.equipment).joinedload(Equipment.equipment_model),
        joinedload(MaintenanceRecord.operation),
        joinedload(MaintenanceRecord.plan),
        joinedload(MaintenanceRecord.technician),
    ).order_by(desc(MaintenanceRecord.maintenance_date), desc(MaintenanceRecord.id)).all()
    equipment = db.query(Equipment).options(
        joinedload(Equipment.equipment_type),
        joinedload(Equipment.equipment_model),
    ).order_by(Equipment.registration_number, Equipment.asset_code).all()

    operations = db.query(MaintenanceOperation).filter(
        MaintenanceOperation.is_active.is_(True)
    ).order_by(MaintenanceOperation.name, MaintenanceOperation.id).all()
    plans = db.query(MaintenancePlan).filter(
        MaintenancePlan.is_active.is_(True),
        MaintenancePlan.is_approved.is_(True),
    ).order_by(MaintenancePlan.name, MaintenancePlan.id).all()

    # الفنيون الفعليون من الورشة الداخلية (لا قائمة ثابتة ولا أسماء تجريبية).
    technicians = list_technicians(db, active_only=True)

    edit_record = None
    edit_id = request.query_params.get("edit")
    if can_manage_records and edit_id and edit_id.isdigit():
        edit_record = db.query(MaintenanceRecord).options(
            joinedload(MaintenanceRecord.operation),
            joinedload(MaintenanceRecord.plan),
        ).filter(MaintenanceRecord.id == int(edit_id)).first()

    # مؤهّل العملية يُحدَّد بطراز العتاد وحده عبر علاقة العملية بالطراز في
    # maintenance_operation_models. لا تُدرَج العمليات المستقلة/العامة غير
    # المرتبطة بأي طراز، لأنها غير قابلة للتنفيذ على عتاد محدد.
    operation_model_ids = {
        operation.id: ",".join(
            str(model.id)
            for model in sorted(operation.equipment_models, key=lambda model: model.id)
        )
        for operation in operations
    }

    # Compute meter_required_by_operation: for each operation, check its model conditions
    # to determine if a meter reading is required for each model
    from app.modules.maintenance.services import operation_conditions_by_model, meter_required_for_condition
    meter_required_by_operation = {}
    for operation in operations:
        # Get all model conditions for this operation (including unset ones)
        conditions = operation_conditions_by_model(db, [operation.id])
        required_by_model = []
        for (op_id, model_id), condition in conditions.items():
            if op_id == operation.id:
                unit = "km"  # Default, but we check both km and hours
                required = meter_required_for_condition(condition, "km") or meter_required_for_condition(condition, "hours")
                required_by_model.append(f"{model_id}:{'1' if required else '0'}")
        # Also include models that are linked to the operation but have no condition row (unset)
        for model in operation.equipment_models:
            if (operation.id, model.id) not in conditions:
                required_by_model.append(f"{model.id}:0")
        meter_required_by_operation[operation.id] = ",".join(required_by_model)

    plan_equipment_ids = {}
    for plan in plans:
        plan_equipment_ids.setdefault(plan.id, set()).add(plan.equipment_model_id)
    return templates.TemplateResponse(
        request=request, name="maintenance_records.html", context={
            "request": request,
            "user": current_user,
            "records": records,
            "equipment": equipment,
            "operations": operations,
            "plans": plans,
            "technicians": technicians,
            "operation_model_ids": operation_model_ids,
            "meter_required_by_operation": meter_required_by_operation,
            "edit_record": edit_record,
            "can_manage_records": can_manage_records,
        },
    )


@router.post("/maintenance/records/create")
def maintenance_record_create(
    equipment_id: int = Form(...),
    operation_id: int = Form(...),
    plan_id: int | None = Form(None),
    maintenance_date: date = Form(...),
    meter_value: str = Form(""),
    work_order: str = Form(""),
    workshop: str = Form(""),
    technician_id: int | None = Form(None),
    description: str = Form(""),
    note: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    records_url = "/maintenance/records"
    equipment = db.query(Equipment).options(
        joinedload(Equipment.equipment_type),
        joinedload(Equipment.equipment_model),
    ).filter(Equipment.id == equipment_id).first()
    if equipment is None:
        return RedirectResponse(f"{records_url}?error=equipment", status_code=status.HTTP_303_SEE_OTHER)

    operation = db.query(MaintenanceOperation).filter(
        MaintenanceOperation.id == operation_id,
        MaintenanceOperation.is_active.is_(True),
    ).first()
    if operation is None:
        return RedirectResponse(f"{records_url}?error=operation_not_found", status_code=status.HTTP_303_SEE_OTHER)

    # Validate operation applicability to equipment using shared function
    validation_error = validate_operation_applicable_to_equipment(db, operation, equipment)
    if validation_error:
        return RedirectResponse(f"{records_url}?error=operation_model", status_code=status.HTTP_303_SEE_OTHER)

    if operation_id not in {
        item.id for item in effective_operations_for_equipment(db, equipment)
    }:
        return RedirectResponse(f"{records_url}?error=operation_model", status_code=status.HTTP_303_SEE_OTHER)

    plan = None
    if plan_id is not None:
        plan = db.query(MaintenancePlan).filter(
            MaintenancePlan.id == plan_id,
            MaintenancePlan.is_active.is_(True),
            MaintenancePlan.is_approved.is_(True),
            MaintenancePlan.equipment_model_id == equipment.equipment_model_id,
        ).first()
        if plan is None:
            return RedirectResponse(f"{records_url}?error=plan_model", status_code=status.HTTP_303_SEE_OTHER)
        linked = db.query(MaintenancePlanOperation.id).filter(
            MaintenancePlanOperation.plan_id == plan.id,
            MaintenancePlanOperation.operation_id == operation.id,
        ).first()
        if linked is None:
            return RedirectResponse(f"{records_url}?error=plan_operation", status_code=status.HTTP_303_SEE_OTHER)

    if maintenance_date > date.today():
        return RedirectResponse(f"{records_url}?error=future_date", status_code=status.HTTP_303_SEE_OTHER)

    work_order_clean = work_order.strip()
    if work_order_clean and not work_order_clean.isdigit():
        return RedirectResponse(f"{records_url}?error=work_order", status_code=status.HTTP_303_SEE_OTHER)

    technician = None
    if technician_id is not None:
        technician = db.query(Technician).filter(Technician.id == technician_id).first()
        if technician is None or not technician.is_active:
            return RedirectResponse(f"{records_url}?error=technician", status_code=status.HTTP_303_SEE_OTHER)

    unit = measurement_unit(equipment)
    meter = None
    if meter_value:
        try:
            meter = Decimal(meter_value)
        except (InvalidOperation, ValueError):
            return RedirectResponse(f"{records_url}?error=meter", status_code=status.HTTP_303_SEE_OTHER)
        if meter < 0:
            return RedirectResponse(f"{records_url}?error=meter", status_code=status.HTTP_303_SEE_OTHER)

    if (unit == "km" and operation.interval_km is not None) or (unit == "hours" and operation.interval_hours is not None):
        if meter is None:
            return RedirectResponse(f"{records_url}?error=meter_required", status_code=status.HTTP_303_SEE_OTHER)

    chronology = chronology_error(db, equipment_id, maintenance_date, meter)
    if chronology:
        return RedirectResponse(f"{records_url}?error=chronology", status_code=status.HTTP_303_SEE_OTHER)

    rec = MaintenanceRecord(
        equipment_id=equipment_id,
        operation_id=operation.id,
        plan_id=plan.id if plan is not None else None,
        maintenance_date=maintenance_date,
        meter_value=meter,
        work_order=work_order_clean or None,
        workshop=workshop.strip() or None,
        technician_id=technician.id if technician is not None else None,
        description=description.strip() or None,
        note=note.strip() or None,
        status="completed",
        created_by_id=current_user.id if current_user else None,
    )
    db.add(rec)
    try:
        db.commit()
    except ValueError as exc:
        db.rollback()
        return RedirectResponse(f"{records_url}?error=validation", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(f"{records_url}?saved=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/maintenance/records/{record_id}/update")
def maintenance_record_update(
    record_id: int,
    equipment_id: int = Form(...),
    operation_id: int = Form(...),
    plan_id: int | None = Form(None),
    maintenance_date: date = Form(...),
    meter_value: str = Form(""),
    work_order: str = Form(""),
    workshop: str = Form(""),
    technician_id: int | None = Form(None),
    description: str = Form(""),
    note: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_min_role(Role.FLEET_MANAGER)),
):
    records_url = "/maintenance/records"
    rec = db.query(MaintenanceRecord).filter(MaintenanceRecord.id == record_id).first()
    equipment = db.query(Equipment).options(
        joinedload(Equipment.equipment_type),
        joinedload(Equipment.equipment_model),
    ).filter(Equipment.id == equipment_id).first()
    operation = db.query(MaintenanceOperation).filter(
        MaintenanceOperation.id == operation_id,
        MaintenanceOperation.is_active.is_(True),
    ).first()
    if rec is None or equipment is None or operation is None:
        return RedirectResponse(f"{records_url}?error=not_found", status_code=status.HTTP_303_SEE_OTHER)

    # Validate operation applicability to equipment using shared function
    validation_error = validate_operation_applicable_to_equipment(db, operation, equipment)
    if validation_error:
        return RedirectResponse(f"{records_url}?error=operation_model", status_code=status.HTTP_303_SEE_OTHER)

    if operation_id not in {item.id for item in effective_operations_for_equipment(db, equipment)}:
        return RedirectResponse(f"{records_url}?error=operation_model", status_code=status.HTTP_303_SEE_OTHER)

    plan = None
    if plan_id is not None:
        plan = db.query(MaintenancePlan).filter(
            MaintenancePlan.id == plan_id,
            MaintenancePlan.is_active.is_(True),
            MaintenancePlan.is_approved.is_(True),
            MaintenancePlan.equipment_model_id == equipment.equipment_model_id,
        ).first()
        if plan is None:
            return RedirectResponse(f"{records_url}?error=plan_model", status_code=status.HTTP_303_SEE_OTHER)
        linked = db.query(MaintenancePlanOperation.id).filter(
            MaintenancePlanOperation.plan_id == plan.id,
            MaintenancePlanOperation.operation_id == operation.id,
        ).first()
        if linked is None:
            return RedirectResponse(f"{records_url}?error=plan_operation", status_code=status.HTTP_303_SEE_OTHER)

    if maintenance_date > date.today():
        return RedirectResponse(f"{records_url}?error=future_date", status_code=status.HTTP_303_SEE_OTHER)

    work_order_clean = work_order.strip()
    if work_order_clean and not work_order_clean.isdigit():
        return RedirectResponse(f"{records_url}?error=work_order", status_code=status.HTTP_303_SEE_OTHER)

    technician = None
    if technician_id is not None:
        technician = db.query(Technician).filter(Technician.id == technician_id).first()
        if technician is None or not technician.is_active:
            return RedirectResponse(f"{records_url}?error=technician", status_code=status.HTTP_303_SEE_OTHER)

    meter = None
    if meter_value:
        try:
            meter = Decimal(meter_value)
        except (InvalidOperation, ValueError):
            return RedirectResponse(f"{records_url}?error=meter", status_code=status.HTTP_303_SEE_OTHER)
        if meter < 0:
            return RedirectResponse(f"{records_url}?error=meter", status_code=status.HTTP_303_SEE_OTHER)

    unit = measurement_unit(equipment)
    if (unit == "km" and operation.interval_km is not None) or (unit == "hours" and operation.interval_hours is not None):
        if meter is None:
            return RedirectResponse(f"{records_url}?error=meter_required", status_code=status.HTTP_303_SEE_OTHER)

    chronology = chronology_error(db, equipment_id, maintenance_date, meter, exclude_id=record_id)
    if chronology:
        return RedirectResponse(f"{records_url}?error=chronology", status_code=status.HTTP_303_SEE_OTHER)

    rec.equipment_id = equipment_id
    rec.operation_id = operation.id
    rec.plan_id = plan.id if plan is not None else None
    rec.maintenance_date = maintenance_date
    rec.meter_value = meter
    rec.work_order = work_order_clean or None
    rec.workshop = workshop.strip() or None
    rec.technician_id = technician.id if technician is not None else None
    rec.description = description.strip() or None
    rec.note = note.strip() or None
    try:
        db.commit()
    except ValueError:
        db.rollback()
        return RedirectResponse(f"{records_url}?error=validation", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(f"{records_url}?saved=updated", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/maintenance/records/{record_id}/delete")
def maintenance_record_delete(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_min_role(Role.FLEET_MANAGER)),
):
    rec = db.query(MaintenanceRecord).filter(MaintenanceRecord.id == record_id).first()
    if rec is None: return RedirectResponse("/maintenance/records?error=not_found", status_code=status.HTTP_303_SEE_OTHER)
    if maintenance_record_delete_reason(rec):
        return RedirectResponse("/maintenance/records?error=protected_record", status_code=status.HTTP_303_SEE_OTHER)
    db.delete(rec)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر حذف سجل الصيانة.") from exc
    return RedirectResponse("/maintenance/records?changed=deleted", status_code=status.HTTP_303_SEE_OTHER)


@router.delete("/api/maintenance/records/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def api_maintenance_record_delete(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_min_role(Role.FLEET_MANAGER)),
):
    """حذف سجل صيانة واحد عبر API مع الحفاظ على البيانات المرتبطة.

    يُرجع استجابة 204 بلا محتوى ولا رأس Content-Type، لتجنب اعتراض
    أدوات الواجهة العامة (مثل edit-manager.js) التي تحاول تحليل JSON من استجابات فارغة.
    """
    from fastapi import Response
    rec = db.query(MaintenanceRecord).filter(MaintenanceRecord.id == record_id).first()
    if rec is None:
        raise HTTPException(status_code=404, detail="سجل الصيانة غير موجود.")
    reason = maintenance_record_delete_reason(rec)
    if reason:
        raise HTTPException(status_code=409, detail=reason)
    db.delete(rec)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر حذف سجل الصيانة.") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/api/maintenance/records/bulk-delete", response_model=dict)
def api_maintenance_records_bulk_delete(
    payload: MaintenanceRecordBulkDelete,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_min_role(Role.FLEET_MANAGER)),
):
    deleted_ids = []
    rejected = []
    try:
        for record_id in payload.record_ids:
            record = db.get(MaintenanceRecord, record_id)
            if record is None:
                rejected.append({
                    "record_id": record_id,
                    "record_label": f"سجل #{record_id}",
                    "reason": "سجل الصيانة غير موجود.",
                })
                continue
            reason = maintenance_record_delete_reason(record)
            if reason:
                rejected.append({
                    "record_id": record.id,
                    "record_label": f"{record.maintenance_date} — {record.operation.name if record.operation else 'سجل قديم'}",
                    "reason": reason,
                })
                continue
            db.delete(record)
            deleted_ids.append(record_id)
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر تنفيذ الحذف الجماعي لسجلات الصيانة.") from exc
    return {"success": len(deleted_ids), "deleted_ids": deleted_ids, "rejected": rejected}


@router.post("/api/maintenance/bulk-delete", response_model=dict)
def api_bulk_delete_operations(
    payload: MaintenanceOperationBulkDelete,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """حذف آمن جزئي لعمليات المكتبة مع بيان سبب رفض كل عملية."""
    operation_ids = payload.operation_ids
    rejected = []
    deleted = 0

    try:
        for op_id in operation_ids:
            operation = db.get(MaintenanceOperation, op_id)
            if operation is None:
                rejected.append({"operation_id": op_id, "operation_name": f"# {op_id}", "reason": "العملية غير موجودة"})
                continue

            # Check if operation is linked to any maintenance records
            has_records = db.query(MaintenanceRecord).filter(
                MaintenanceRecord.operation_id == op_id
            ).first() is not None

            if has_records:
                rejected.append({
                    "operation_id": op_id,
                    "operation_name": operation.name,
                    "reason": "لا يمكن حذف العملية لأنها مرتبطة بسجل صيانة. عطّل العملية بدلًا من حذفها."
                })
                continue

            # Check if operation is linked to any plans
            has_plan_links = db.query(MaintenancePlanOperation).filter(
                MaintenancePlanOperation.operation_id == op_id
            ).first() is not None

            if has_plan_links:
                rejected.append({
                    "operation_id": op_id,
                    "operation_name": operation.name,
                    "reason": "لا يمكن حذف العملية لأنها مرتبطة بخطط الصيانة. أزل ارتباطها بالخطة أولًا."
                })
                continue

            db.delete(operation)
            deleted += 1
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر تنفيذ الحذف الجماعي لعمليات الصيانة.") from exc

    return {"success": deleted, "rejected": rejected}


@router.get("/maintenance/due", response_class=HTMLResponse)
def maintenance_due_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    equipment = db.query(Equipment).options(joinedload(Equipment.equipment_type), joinedload(Equipment.equipment_model)).all()
    model_ids = {eq.equipment_model_id for eq in equipment if eq.equipment_model_id is not None}
    approved_model_ids = {
        model_id for (model_id,) in db.query(MaintenancePlan.equipment_model_id).filter(
            MaintenancePlan.equipment_model_id.in_(model_ids or {-1}),
            MaintenancePlan.is_active.is_(True),
            MaintenancePlan.is_approved.is_(True),
        ).distinct().all()
    }
    unapproved_models = sorted({
        eq.equipment_model.name
        for eq in equipment
        if eq.equipment_model_id is not None
        and eq.equipment_model is not None
        and eq.equipment_model_id not in approved_model_ids
    })
    readings = latest_readings(db)
    records = latest_records(db)
    due_rows = []
    plan_groups = []
    standalone_rows = []
    group_map: dict = {}
    tasks_by_model: dict = {}

    for eq in equipment:
        current_value = current_meter_value(eq, readings.get(eq.id))
        model_id = eq.equipment_model_id
        if model_id is not None and model_id not in tasks_by_model:
            tasks_by_model[model_id] = operation_tasks_for_model(db, model_id)
        # كل مهمة تحمل سياقها: عملية خطة بشرط خطتها، أو عملية مستقلة بشرط طرازها.
        for task in tasks_by_model.get(model_id, []):
            operation = task.operation
            rec = records.get((eq.id, operation.id))
            state, css, remaining, meta = status_for(operation, eq, rec, current_value, condition=task.condition)
            if state not in ("مستحقة الآن", "تقترب", "بلا سجل"):
                continue
            row = {
                "equipment": eq,
                "operation": operation,
                "record": rec,
                "current": current_value,
                "unit": measurement_unit(eq),
                "remaining": remaining,
                "remaining_days": meta.get("remaining_days"),
                "state": state,
                "css": css,
                "priority": priority_for(state, remaining, meta),
                "contradiction": contradiction_for(eq, rec, current_value, db),
            }
            due_rows.append(row)
            if task.plan is not None:
                group = group_map.get(task.plan.id)
                if group is None:
                    group = {"plan": task.plan, "rows": []}
                    group_map[task.plan.id] = group
                    plan_groups.append(group)
                group["rows"].append(row)
            else:
                standalone_rows.append(row)

    due_rows.sort(key=lambda r: (
        r["priority"],
        r["remaining"] if r["remaining"] is not None else Decimal("999999999"),
        r["remaining_days"] if r["remaining_days"] is not None else 999999999,
        r["equipment"].registration_number or r["equipment"].asset_code or "",
    ))

    plan_groups.sort(key=lambda group: (group["plan"].name, group["plan"].id))
    return templates.TemplateResponse(
        request=request, name="maintenance_due.html", context={
            "request": request,
            "user": current_user,
            "rows": due_rows,
            "plan_groups": plan_groups,
            "standalone_rows": standalone_rows,
            "unapproved_models": unapproved_models,
        },
    )

# JSON API for the operation-first maintenance library.
@router.get("/api/maintenance/operation-groups", response_model=list[MaintenanceOperationGroupOut])
def api_operation_groups(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(MaintenanceOperationGroup).order_by(MaintenanceOperationGroup.sort_order, MaintenanceOperationGroup.name, MaintenanceOperationGroup.id).all()

@router.post("/api/maintenance/operation-groups", response_model=MaintenanceOperationGroupOut, status_code=status.HTTP_201_CREATED)
def api_operation_group_create(payload: MaintenanceOperationGroupCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    group = MaintenanceOperationGroup(**payload.model_dump()); db.add(group)
    try: db.commit(); db.refresh(group)
    except Exception as exc: db.rollback(); raise HTTPException(status_code=409, detail="اسم مجموعة شروط الصيانة مستخدم مسبقًا.") from exc
    return group

@router.put("/api/maintenance/operation-groups/{group_id}", response_model=MaintenanceOperationGroupOut)
def api_operation_group_update(group_id: int, payload: MaintenanceOperationGroupUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    group = db.get(MaintenanceOperationGroup, group_id)
    if group is None: raise HTTPException(status_code=404, detail="مجموعة شروط الصيانة غير موجودة.")
    for key, value in payload.model_dump().items(): setattr(group, key, value)
    try: db.commit(); db.refresh(group)
    except Exception as exc: db.rollback(); raise HTTPException(status_code=409, detail="اسم مجموعة شروط الصيانة مستخدم مسبقًا.") from exc
    return group

@router.delete("/api/maintenance/operation-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)

def api_operation_group_delete(group_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):

    group = db.get(MaintenanceOperationGroup, group_id)

    if group is None:

        raise HTTPException(status_code=404, detail="مجموعة شروط الصيانة غير موجودة.")

    db.delete(group)

    try:

        db.commit()

    except Exception as exc:

        db.rollback()

        raise HTTPException(status_code=409, detail="تعذر حذف مجموعة شروط الصيانة.") from exc

    return None



@router.get("/api/maintenance/equipment/models")

def api_equipment_models(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):

    """Return all equipment models for operation-model association."""

    models = db.query(EquipmentModel).options(

        joinedload(EquipmentModel.equipment_type),

        joinedload(EquipmentModel.brand)

    ).order_by(EquipmentModel.name).all()

    return [{"id": m.id, "name": m.name, "type": m.equipment_type.name if m.equipment_type else "", "brand": m.brand.name if m.brand else ""} for m in models]



@router.delete("/api/maintenance/operation-groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def api_operation_group_delete(group_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    group = db.get(MaintenanceOperationGroup, group_id)
    if group is None:
        raise HTTPException(status_code=404, detail="مجموعة شروط الصيانة غير موجودة.")
    db.delete(group)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر حذف مجموعة شروط الصيانة.") from exc
    return None

@router.delete("/api/maintenance/operations/{operation_id}", status_code=status.HTTP_204_NO_CONTENT)
def api_operation_delete(operation_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    operation = db.get(MaintenanceOperation, operation_id)
    if operation is None:
        raise HTTPException(status_code=404, detail="عملية الصيانة غير موجودة.")
    if db.query(MaintenancePlanOperation.id).filter(MaintenancePlanOperation.operation_id == operation_id).first() is not None:
        raise HTTPException(status_code=409, detail="لا يمكن حذف العملية لأنها مرتبطة بخطة صيانة. عطّلها بدلًا من حذفها.")
    if db.query(MaintenanceRecord.id).filter(MaintenanceRecord.operation_id == operation_id).first() is not None:
        raise HTTPException(status_code=409, detail="لا يمكن حذف العملية لأنها مستخدمة في سجل الصيانة. عطّلها بدلًا من حذفها.")
    db.delete(operation)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر حذف عملية الصيانة.") from exc
    return None


@router.get("/api/maintenance/operations", response_model=list[MaintenanceOperationOut])
def api_operations(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    operations = db.query(MaintenanceOperation).order_by(MaintenanceOperation.name, MaintenanceOperation.id).all()
    return operations_payload(db, operations)

@router.post("/api/maintenance/operations", response_model=MaintenanceOperationOut, status_code=status.HTTP_201_CREATED)
def api_operation_create(payload: MaintenanceOperationCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    data = payload.model_dump()
    if data.get("group_id") is not None and db.get(MaintenanceOperationGroup, data["group_id"]) is None:
        raise HTTPException(status_code=404, detail="مجموعة شروط الصيانة غير موجودة.")

    equipment_model_conditions = data.pop("equipment_model_conditions", [])

    # Legacy interval fields on the operation are not used; they remain None.
    # The authoritative conditions are stored per-model in maintenance_operation_models.
    # warning_km and warning_days are the unified warning fields at operation level - KEEP them.
    for field in ("interval_km", "interval_hours", "interval_days"):
        data.pop(field, None)

    operation = MaintenanceOperation(**data)
    db.add(operation)
    db.flush()  # Get the operation ID

    if equipment_model_conditions:
        _sync_operation_model_conditions(db, operation, equipment_model_conditions)

    try:
        db.commit()
        db.refresh(operation)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر إنشاء عملية الصيانة.") from exc
    return operations_payload(db, [operation])[0]

@router.put("/api/maintenance/operations/{operation_id}", response_model=MaintenanceOperationOut)
def api_operation_update(operation_id: int, payload: MaintenanceOperationUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    operation = db.get(MaintenanceOperation, operation_id)
    if operation is None: raise HTTPException(status_code=404, detail="عملية الصيانة غير موجودة.")
    data = payload.model_dump()
    if data.get("group_id") is not None and db.get(MaintenanceOperationGroup, data["group_id"]) is None:
        raise HTTPException(status_code=404, detail="مجموعة شروط الصيانة غير موجودة.")

    # Handle equipment_model_conditions separately
    equipment_model_conditions = data.pop("equipment_model_conditions", None)

    # Legacy interval fields on the operation are not used; they remain unchanged.
    # The authoritative conditions are stored per-model in maintenance_operation_models.
    # warning_km and warning_days are the unified warning fields at operation level - KEEP them.
    for field in ("interval_km", "interval_hours", "interval_days"):
        data.pop(field, None)

    for key, value in data.items(): setattr(operation, key, value)

    # Update equipment_model_conditions if provided, and validate against plans
    if equipment_model_conditions is not None:
        # Sync the model conditions (this will update the maintenance_operation_models table)
        _sync_operation_model_conditions(db, operation, equipment_model_conditions)

        # Check if any affected plan's model is no longer in the operation's models
        affected_plans = db.query(MaintenancePlan).join(
            MaintenancePlanOperation, MaintenancePlanOperation.plan_id == MaintenancePlan.id
        ).filter(MaintenancePlanOperation.operation_id == operation.id).all()
        
        # Get the updated model IDs from the synced conditions
        current_model_ids = {m.id for m in operation.equipment_models}
        
        model_errors = []
        for plan in affected_plans:
            if plan.equipment_model_id not in current_model_ids:
                model_errors.append(f"خطة '{plan.name}' (ID: {plan.id}) تتطلب طراز العتاد {plan.equipment_model_id} الذي لم يعد مرتبطًا بالعملية")
        
        if model_errors:
            # We can't easily rollback the _sync_operation_model_conditions, so we raise an error
            # The transaction will be rolled back by the exception handler
            raise HTTPException(
                status_code=409,
                detail="تعذر تعديل العملية: تغيير الطرازات المرتبطة يتعارض مع الخطط التالية:\n" + "\n".join(model_errors)
            )

    # Plans that contain this operation no longer depend on its per-model
    # condition: each plan operation is governed by the plan's condition. Editing
    # the operation therefore neither rejects nor redefines any plan; plans that
    # contain it are only flagged for a fresh review.
    affected_plans = db.query(MaintenancePlan).join(
        MaintenancePlanOperation, MaintenancePlanOperation.plan_id == MaintenancePlan.id
    ).filter(MaintenancePlanOperation.operation_id == operation.id).all()
    for plan in affected_plans:
        plan.is_approved = False

    try: db.commit(); db.refresh(operation)
    except Exception as exc: db.rollback(); raise HTTPException(status_code=409, detail="تعذر تعديل عملية الصيانة.") from exc
    return operations_payload(db, [operation])[0]


# Operation-Model relationship endpoints
@router.get("/api/maintenance/operations/{operation_id}/models", response_model=list[dict])
def api_operation_models(operation_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    operation = db.get(MaintenanceOperation, operation_id)
    if operation is None:
        raise HTTPException(status_code=404, detail="عملية الصيانة غير موجودة.")
    return [{"id": m.id, "name": m.name} for m in operation.equipment_models]


@router.post("/api/maintenance/operations/{operation_id}/models", status_code=status.HTTP_201_CREATED)
def api_operation_add_model(operation_id: int, equipment_model_id: int = Form(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    operation = db.get(MaintenanceOperation, operation_id)
    if operation is None:
        raise HTTPException(status_code=404, detail="عملية الصيانة غير موجودة.")
    model = db.get(EquipmentModel, equipment_model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="طراز العتاد غير موجود.")
    if model in operation.equipment_models:
        raise HTTPException(status_code=409, detail="العملية مرتبطة بهذا الطراز مسبقًا.")
    operation.equipment_models.append(model)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر إضافة الطراز للعملية.") from exc
    return {"operation_id": operation.id, "equipment_model_id": model.id, "name": model.name}


@router.delete("/api/maintenance/operations/{operation_id}/models/{equipment_model_id}", status_code=status.HTTP_204_NO_CONTENT)
def api_operation_remove_model(operation_id: int, equipment_model_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    operation = db.get(MaintenanceOperation, operation_id)
    if operation is None:
        raise HTTPException(status_code=404, detail="عملية الصيانة غير موجودة.")
    model = db.get(EquipmentModel, equipment_model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="طراز العتاد غير موجود.")
    if model not in operation.equipment_models:
        raise HTTPException(status_code=404, detail="العملية غير مرتبطة بهذا الطراز.")
    affected_plans = db.query(MaintenancePlan).join(
        MaintenancePlanOperation,
        MaintenancePlanOperation.plan_id == MaintenancePlan.id,
    ).filter(
        MaintenancePlan.equipment_model_id == model.id,
        MaintenancePlanOperation.operation_id == operation.id,
        MaintenancePlan.is_approved.is_(True),
    ).all()
    for plan in affected_plans:
        plan.is_approved = False
    operation.equipment_models.remove(model)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر إزالة الطراز من العملية.") from exc
    return None

@router.get("/api/maintenance/plans", response_model=list[MaintenancePlanOut])
def api_plans(equipment_model_id: int | None = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = db.query(MaintenancePlan)
    if equipment_model_id is not None: query = query.filter(MaintenancePlan.equipment_model_id == equipment_model_id)
    return query.order_by(MaintenancePlan.name, MaintenancePlan.id).all()

@router.post("/api/maintenance/plans", response_model=MaintenancePlanOut, status_code=status.HTTP_201_CREATED)
def api_plan_create(payload: MaintenancePlanCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if db.get(EquipmentModel, payload.equipment_model_id) is None: raise HTTPException(status_code=404, detail="طراز العتاد غير موجود.")
    plan = MaintenancePlan(**payload.model_dump()); db.add(plan)
    try: db.commit(); db.refresh(plan)
    except Exception as exc: db.rollback(); raise HTTPException(status_code=409, detail="تعذر إنشاء خطة الصيانة.") from exc
    return plan

@router.post("/api/maintenance/plans/bulk-delete", response_model=dict)
def api_plans_bulk_delete(payload: MaintenancePlanBulkDelete, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """حذف الخطط الآمنة، مع رفض الخطط التي تحفظ سياق تنفيذ تاريخي.

    كل رفض يعيد معرّف الخطة وسبب منع حذفها. لا يُحذف تعريف عملية من المكتبة.
    """
    deleted = 0
    rejected: list[dict] = []
    try:
        for plan_id in payload.plan_ids:
            plan = db.get(MaintenancePlan, plan_id)
            if plan is None:
                rejected.append({"plan_id": plan_id, "plan_name": f"# {plan_id}", "reason": "خطة الصيانة غير موجودة"})
                continue
            try:
                _delete_plan(db, plan)
            except ValueError as exc:
                rejected.append({"plan_id": plan.id, "plan_name": plan.name, "reason": str(exc)})
            else:
                deleted += 1
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر تنفيذ الحذف الجماعي لخطط الصيانة.") from exc
    return {"success": deleted, "rejected": rejected}

@router.put("/api/maintenance/plans/{plan_id}", response_model=MaintenancePlanOut)
def api_plan_update(plan_id: int, payload: MaintenancePlanUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    plan = db.get(MaintenancePlan, plan_id)
    if plan is None: raise HTTPException(status_code=404, detail="خطة الصيانة غير موجودة.")
    if db.get(EquipmentModel, payload.equipment_model_id) is None: raise HTTPException(status_code=404, detail="طراز العتاد غير موجود.")

    # Capture original values for potential rollback
    original_interval_km = plan.interval_km
    original_interval_hours = plan.interval_hours
    original_interval_days = plan.interval_days

    for key, value in payload.model_dump().items(): setattr(plan, key, value)

    # Any plan edit requires explicit re-approval before it drives follow-ups.
    plan.is_approved = False
    try: db.commit(); db.refresh(plan)
    except Exception as exc: db.rollback(); raise HTTPException(status_code=409, detail="تعذر تعديل خطة الصيانة.") from exc
    return plan

@router.delete("/api/maintenance/plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def api_plan_delete(plan_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """حذف خطة صيانة لا ترتبط بتنفيذ تاريخي فقط."""
    plan = db.get(MaintenancePlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="خطة الصيانة غير موجودة.")
    try:
        _delete_plan(db, plan)
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر حذف خطة الصيانة.") from exc
    return None

@router.post("/api/maintenance/plans/{plan_id}/approve", response_model=MaintenancePlanOut)
def api_plan_approve(plan_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    plan = db.get(MaintenancePlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="خطة الصيانة غير موجودة.")
    if not plan.is_active:
        raise HTTPException(status_code=409, detail="لا يمكن اعتماد خطة صيانة متوقفة.")
    operation_count = db.query(MaintenancePlanOperation.id).join(
        MaintenanceOperation, MaintenanceOperation.id == MaintenancePlanOperation.operation_id
    ).filter(
        MaintenancePlanOperation.plan_id == plan.id,
        MaintenanceOperation.is_active.is_(True),
    ).count()
    if operation_count == 0:
        raise HTTPException(status_code=409, detail="أضف عملية صيانة مفعلة واحدة على الأقل قبل اعتماد الخطة.")
    plan.is_approved = True
    try:
        db.commit()
        db.refresh(plan)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر اعتماد خطة الصيانة.") from exc
    return plan


@router.get("/api/maintenance/plans/{plan_id}/operations", response_model=list[MaintenancePlanOperationOut])
def api_plan_operations(plan_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if db.get(MaintenancePlan, plan_id) is None: raise HTTPException(status_code=404, detail="خطة الصيانة غير موجودة.")
    return db.query(MaintenancePlanOperation).filter(MaintenancePlanOperation.plan_id == plan_id).order_by(MaintenancePlanOperation.sort_order, MaintenancePlanOperation.id).all()


@router.post("/api/maintenance/plans/{plan_id}/operations", response_model=MaintenancePlanOperationOut, status_code=status.HTTP_201_CREATED)
def api_plan_operation_add(plan_id: int, payload: MaintenancePlanOperationCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if payload.plan_id != plan_id:
        raise HTTPException(status_code=400, detail="رقم الخطة في الطلب لا يطابق المسار.")
    plan = db.get(MaintenancePlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="خطة الصيانة غير موجودة.")
    if not plan.is_active:
        raise HTTPException(status_code=409, detail="لا يمكن إضافة عملية إلى خطة صيانة غير مفعلة.")
    operation = db.get(MaintenanceOperation, payload.operation_id)
    if operation is None:
        raise HTTPException(status_code=404, detail="عملية الصيانة غير موجودة.")
    if not operation.is_active:
        raise HTTPException(status_code=409, detail="لا يمكن إضافة عملية صيانة غير مفعلة إلى الخطة.")

    # Check if operation is linked to the plan's equipment model
    model = db.get(EquipmentModel, plan.equipment_model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="طراز العتاد للخطة غير موجود.")

    # A plan operation inherits the plan's condition, so no independent per-model
    # condition is required to add it. Membership only needs the operation to be
    # active (checked above); the plan condition is the source of truth from then
    # on and is never written back to the operation.
    if model not in operation.equipment_models:
        operation.equipment_models.append(model)

    link = MaintenancePlanOperation(**payload.model_dump())
    db.add(link)
    plan.is_approved = False
    try:
        db.commit()
        db.refresh(link)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="العملية مرتبطة بهذه الخطة مسبقًا أو أن البيانات غير صالحة.") from exc
    return link

@router.delete("/api/maintenance/plans/{plan_id}/operations/{operation_id}", status_code=status.HTTP_204_NO_CONTENT)
def api_plan_operation_remove(
    plan_id: int,
    operation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plan = db.get(MaintenancePlan, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="خطة الصيانة غير موجودة.")
    link = db.query(MaintenancePlanOperation).filter(
        MaintenancePlanOperation.plan_id == plan_id,
        MaintenancePlanOperation.operation_id == operation_id,
    ).first()
    if link is None:
        raise HTTPException(status_code=404, detail="العملية غير مرتبطة بهذه الخطة.")
    db.delete(link)
    plan.is_approved = False
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر إزالة العملية من الخطة.") from exc
    return None


@router.get("/api/maintenance/execution", response_model=list[MaintenanceRecordOut])
def api_execution_records(
    equipment_id: int | None = None,
    operation_id: int | None = None,
    plan_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(MaintenanceRecord)
    if equipment_id is not None: query = query.filter(MaintenanceRecord.equipment_id == equipment_id)
    if operation_id is not None: query = query.filter(MaintenanceRecord.operation_id == operation_id)
    if plan_id is not None: query = query.filter(MaintenanceRecord.plan_id == plan_id)
    return query.order_by(MaintenanceRecord.maintenance_date.desc(), MaintenanceRecord.id.desc()).all()


@router.post("/api/maintenance/execution", response_model=MaintenanceRecordOut, status_code=status.HTTP_201_CREATED)
def api_execution_create(
    payload: MaintenanceRecordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    equipment = db.query(Equipment).options(joinedload(Equipment.equipment_type), joinedload(Equipment.equipment_model)).filter(Equipment.id == payload.equipment_id).first()
    if equipment is None:
        raise HTTPException(status_code=404, detail="العتاد المحدد غير موجود.")
    if payload.maintenance_date > date.today():
        raise HTTPException(status_code=400, detail="لا يمكن تسجيل صيانة بتاريخ مستقبلي.")

    operation = db.get(MaintenanceOperation, payload.operation_id) if payload.operation_id is not None else None
    plan = db.get(MaintenancePlan, payload.plan_id) if payload.plan_id is not None else None

    if operation is None:
        raise HTTPException(status_code=400, detail="يجب تحديد عملية الصيانة.")
    if operation is not None and not operation.is_active:
        raise HTTPException(status_code=409, detail="عملية الصيانة غير مفعلة.")
    if plan is not None:
        if not plan.is_active:
            raise HTTPException(status_code=409, detail="خطة الصيانة غير مفعلة.")
        if not plan.is_approved:
            raise HTTPException(status_code=409, detail="لا يمكن ربط سجل تنفيذ بخطة غير معتمدة.")
        if plan.equipment_model_id != equipment.equipment_model_id:
            raise HTTPException(status_code=409, detail="خطة الصيانة لا تخص طراز العتاد المحدد.")

    # Validate operation applicability to equipment using shared function
    validation_error = validate_operation_applicable_to_equipment(db, operation, equipment)
    if validation_error:
        raise HTTPException(status_code=409, detail=validation_error)

    # If a plan is specified, verify the operation belongs to that plan
    if plan is not None:
        linked = db.query(MaintenancePlanOperation.id).filter(
            MaintenancePlanOperation.plan_id == plan.id,
            MaintenancePlanOperation.operation_id == operation.id,
        ).first()
        if linked is None:
            raise HTTPException(status_code=409, detail="العملية المختارة غير مرتبطة بالخطة المحددة.")

    # Validate the technician reference when supplied.
    technician = None
    if payload.technician_id is not None:
        technician = db.get(Technician, payload.technician_id)
        if technician is None or not technician.is_active:
            raise HTTPException(status_code=409, detail="الفني المحدد غير موجود أو غير نشط.")

    # The meter requirement follows the governing condition: a plan record uses
    # the plan's condition, a standalone record uses the operation's model condition.
    from app.modules.maintenance.services import operation_condition_for_model, meter_required_for_condition
    if plan is not None:
        model_condition = plan_condition(plan)
    else:
        model_condition = operation_condition_for_model(db, operation.id, equipment.equipment_model_id)
    unit = measurement_unit(equipment)
    if payload.meter_value is not None and payload.meter_value < 0:
        raise HTTPException(status_code=400, detail="لا يمكن أن تكون قراءة العداد سالبة.")
    if meter_required_for_condition(model_condition, unit) and payload.meter_value is None:
        raise HTTPException(status_code=400, detail="يجب إدخال قراءة العداد لهذه العملية.")

    chronology = chronology_error(db, payload.equipment_id, payload.maintenance_date, payload.meter_value)
    if chronology:
        raise HTTPException(status_code=409, detail=chronology)

    record = MaintenanceRecord(
        equipment_id=payload.equipment_id,
        operation_id=operation.id if operation is not None else None,
        plan_id=payload.plan_id,
        maintenance_date=payload.maintenance_date,
        reported_date=payload.reported_date or payload.maintenance_date,
        meter_value=payload.meter_value,
        work_order=payload.work_order,
        workshop=payload.workshop,
        technician_id=technician.id if technician is not None else None,
        status=payload.status or "completed",
        is_scheduled=payload.is_scheduled,
        description=payload.description,
        note=payload.note,
        created_by_id=current_user.id if current_user else None,
    )
    db.add(record)
    try:
        db.commit()
        db.refresh(record)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر تسجيل تنفيذ الصيانة؛ تحقق من عدم تكرار السجل والبيانات المرتبطة.") from exc
    return record


@router.get("/api/maintenance/plan-status")
def api_plan_status(
    equipment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    equipment = db.query(Equipment).options(joinedload(Equipment.equipment_type), joinedload(Equipment.equipment_model)).filter(Equipment.id == equipment_id).first()
    if equipment is None:
        raise HTTPException(status_code=404, detail="العتاد المحدد غير موجود.")
    readings = latest_readings(db)
    current_value = current_meter_value(equipment, readings.get(equipment.id))
    latest_plans = latest_plan_records(db)
    rows = []
    for plan in effective_plans_for_equipment(db, equipment):
        record = latest_plans.get((equipment.id, plan.id))
        state, css, remaining, meta = plan_status_for(plan, equipment, record, current_value)
        rows.append({
            "plan_id": plan.id,
            "name": plan.name,
            "equipment_model_id": plan.equipment_model_id,
            "interval_km": plan.interval_km,
            "interval_hours": plan.interval_hours,
            "interval_days": plan.interval_days,
            "state": state,
            "css": css,
            "remaining": remaining,
            "remaining_days": meta.get("remaining_days"),
            "next_meter": meta.get("next_meter"),
            "next_date": meta.get("next_date"),
            "last_execution_date": record.maintenance_date if record else None,
            "last_execution_meter": record.meter_value if record else None,
        })
    return rows


@router.post("/api/maintenance/plan-execution", response_model=list[MaintenanceRecordOut], status_code=status.HTTP_201_CREATED)
def api_plan_execution_create(
    payload: MaintenancePlanExecutionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    equipment = db.query(Equipment).options(joinedload(Equipment.equipment_type), joinedload(Equipment.equipment_model)).filter(Equipment.id == payload.equipment_id).first()
    if equipment is None:
        raise HTTPException(status_code=404, detail="العتاد المحدد غير موجود.")
    plan = db.get(MaintenancePlan, payload.plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="خطة الصيانة غير موجودة.")
    if not plan.is_active:
        raise HTTPException(status_code=409, detail="خطة الصيانة غير مفعلة.")
    if not plan.is_approved:
        raise HTTPException(status_code=409, detail="لا يمكن تنفيذ خطة غير معتمدة.")
    if plan.equipment_model_id != equipment.equipment_model_id:
        raise HTTPException(status_code=409, detail="خطة الصيانة لا تخص طراز العتاد المحدد.")
    if payload.maintenance_date > date.today():
        raise HTTPException(status_code=400, detail="لا يمكن تسجيل صيانة بتاريخ مستقبلي.")

    selected_ids = list(dict.fromkeys(payload.operation_ids))
    links = (
        db.query(MaintenancePlanOperation)
        .join(MaintenanceOperation, MaintenanceOperation.id == MaintenancePlanOperation.operation_id)
        .filter(
            MaintenancePlanOperation.plan_id == plan.id,
            MaintenanceOperation.is_active.is_(True),
        )
        .all()
    )
    active_links = {}
    for link in links:
        active_links[link.operation_id] = link
    invalid_ids = [operation_id for operation_id in selected_ids if operation_id not in active_links]
    if invalid_ids:
        raise HTTPException(status_code=409, detail="توجد عملية محددة ليست ضمن العمليات المفعلة لهذه الخطة.")

    # Verify all selected operations are linked to the equipment's model
    for operation_id in selected_ids:
        operation = active_links[operation_id].operation
        validation_error = validate_operation_applicable_to_equipment(db, operation, equipment)
        if validation_error:
            raise HTTPException(status_code=409, detail=f"عملية {operation.name}: {validation_error}")

    unit = measurement_unit(equipment)
    if payload.meter_value is not None and payload.meter_value < 0:
        raise HTTPException(status_code=400, detail="لا يمكن أن تكون قراءة العداد سالبة.")
    # كل عمليات الخطة ترث شرط الخطة، فتتطلب قراءة العداد وفق محاور الخطة.
    from app.modules.maintenance.services import meter_required_for_condition
    plan_cond = plan_condition(plan)
    for operation_id in selected_ids:
        operation = active_links[operation_id].operation
        if meter_required_for_condition(plan_cond, unit) and payload.meter_value is None:
            raise HTTPException(status_code=400, detail=f"يجب إدخال قراءة العداد للعملية: {operation.name}.")

    chronology = chronology_error(db, payload.equipment_id, payload.maintenance_date, payload.meter_value)
    if chronology:
        raise HTTPException(status_code=409, detail=chronology)

    records = []
    try:
        for operation_id in selected_ids:
            operation = active_links[operation_id].operation
            record = MaintenanceRecord(
                equipment_id=payload.equipment_id,
                operation_id=operation.id,
                plan_id=plan.id,
                maintenance_date=payload.maintenance_date,
                reported_date=payload.reported_date or payload.maintenance_date,
                meter_value=payload.meter_value,
                work_order=payload.work_order,
                workshop=payload.workshop,
                status=payload.status or "completed",
                # تنفيذ الخطة هو صيانة فعلية؛ لا يُسجل كسجل مجدول.
                is_scheduled=False,
                description=payload.description,
                created_by_id=current_user.id if current_user else None,
            )
            db.add(record)
            records.append(record)
        db.commit()
        for record in records:
            db.refresh(record)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="تعذر تسجيل العمليات المحددة؛ لم يتم حفظ أي عملية من الخطة.") from exc
    return records
