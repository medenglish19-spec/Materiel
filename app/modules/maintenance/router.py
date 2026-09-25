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
from app.modules.equipment_types.models import EquipmentModel, EquipmentType
from app.modules.maintenance.models import (MaintenanceOperation, MaintenanceOperationGroup, MaintenanceOperationRuleMap, MaintenancePlan, MaintenancePlanOperation, MaintenanceRecord, MaintenanceRule)
from app.modules.maintenance.schemas import (MaintenanceOperationCreate, MaintenanceOperationGroupCreate, MaintenanceOperationGroupOut, MaintenanceOperationGroupUpdate, MaintenanceOperationOut, MaintenanceOperationUpdate, MaintenancePlanCreate, MaintenancePlanOperationCreate, MaintenancePlanOperationOut, MaintenancePlanOut, MaintenancePlanUpdate)
from app.modules.maintenance.services import (
    chronology_error,
    contradiction_for,
    current_meter_value,
    effective_rules_for_equipment,
    get_effective_rule_for_equipment,
    latest_readings,
    latest_records,
    measurement_unit,
    priority_for,
    status_for,
)
from app.modules.users.models import User

router = APIRouter()
templates = get_module_templates("app/modules/maintenance/templates")


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
        )
        .order_by(MaintenanceRule.id.desc())
        .all()
    )
    types = db.query(EquipmentType).order_by(EquipmentType.name).all()
    models = db.query(EquipmentModel).options(joinedload(EquipmentModel.brand), joinedload(EquipmentModel.equipment_type)).order_by(EquipmentModel.name).all()
    record_counts = {r.id: db.query(MaintenanceRecord.id).filter(MaintenanceRecord.rule_id == r.id).count() for r in rules}
    edit_rule = None
    edit_id = request.query_params.get("edit")
    if edit_id and edit_id.isdigit():
        edit_rule = db.query(MaintenanceRule).filter(MaintenanceRule.id == int(edit_id)).first()
    return templates.TemplateResponse(
        "maintenance_rules_model_only.html",
        {
            "request": request,
            "user": current_user,
            "rules": rules,
            "types": types,
            "models": models,
            "record_counts": record_counts,
            "edit_rule": edit_rule,
        },
    )


@router.post("/maintenance/rules/create")
def maintenance_rule_create(
    name: str = Form(...),
    equipment_model_id: int = Form(...),
    interval_km: str = Form(""),
    interval_hours: str = Form(""),
    interval_days: str = Form(""),
    warning_km: str = Form("500"),
    warning_days: str = Form("7"),
    description: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    def dec(v):
        try:
            return Decimal(v) if v else None
        except (InvalidOperation, ValueError):
            return None

    model = db.query(EquipmentModel).options(joinedload(EquipmentModel.equipment_type)).filter(EquipmentModel.id == equipment_model_id).first()
    if model is None:
        return RedirectResponse("/maintenance/rules?error=equipment_model", status_code=status.HTTP_303_SEE_OTHER)

    km = dec(interval_km)
    hours = dec(interval_hours)
    days = int(interval_days) if interval_days else None
    if model.equipment_type.measurement_unit == "km":
        hours = None
    elif model.equipment_type.measurement_unit == "hours":
        km = None
    if not name.strip() or not (km or hours or days):
        return RedirectResponse("/maintenance/rules?error=invalid", status_code=status.HTTP_303_SEE_OTHER)

    rule = MaintenanceRule(
        name=name.strip(),
        equipment_type_id=model.equipment_type_id,
        equipment_model_id=model.id,
        interval_km=km,
        interval_hours=hours,
        interval_days=days,
        warning_km=dec(warning_km),
        warning_days=int(warning_days) if warning_days else None,
        is_active=True,
        description=description.strip() or None,
    )
    db.add(rule)
    db.commit()
    return RedirectResponse("/maintenance/rules?saved=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/maintenance/rules/{rule_id}/update")
def maintenance_rule_update(
    rule_id: int,
    name: str = Form(...),
    equipment_model_id: int = Form(...),
    interval_km: str = Form(""),
    interval_hours: str = Form(""),
    interval_days: str = Form(""),
    warning_km: str = Form("500"),
    warning_days: str = Form("7"),
    description: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rule = db.query(MaintenanceRule).filter(MaintenanceRule.id == rule_id).first()
    model = db.query(EquipmentModel).options(joinedload(EquipmentModel.equipment_type)).filter(EquipmentModel.id == equipment_model_id).first()
    if rule is None or model is None:
        return RedirectResponse("/maintenance/rules?error=not_found", status_code=status.HTTP_303_SEE_OTHER)

    def dec(v):
        try:
            return Decimal(v) if v else None
        except (InvalidOperation, ValueError):
            return None

    km = dec(interval_km)
    hours = dec(interval_hours)
    days = int(interval_days) if interval_days else None
    if model.equipment_type.measurement_unit == "km":
        hours = None
    elif model.equipment_type.measurement_unit == "hours":
        km = None
    if not name.strip() or not (km or hours or days):
        return RedirectResponse(f"/maintenance/rules?edit={rule_id}&error=invalid", status_code=status.HTTP_303_SEE_OTHER)

    rule.name = name.strip()
    rule.equipment_type_id = model.equipment_type_id
    rule.equipment_model_id = model.id
    rule.interval_km = km
    rule.interval_hours = hours
    rule.interval_days = days
    rule.warning_km = dec(warning_km)
    rule.warning_days = int(warning_days) if warning_days else None
    rule.description = description.strip() or None
    rule.is_active = True
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
    effective_rule_equipment_ids = {rule_id: ",".join(str(equipment_id) for equipment_id in sorted(equipment_ids)) for rule_id, equipment_ids in effective_rule_equipment_ids.items()}
    return templates.TemplateResponse("maintenance_records.html", {"request": request, "user": current_user, "records": records, "equipment": equipment, "rules": rules, "effective_rule_equipment_ids": effective_rule_equipment_ids, "edit_record": edit_record})


@router.post("/maintenance/records/create")
def maintenance_record_create(equipment_id: int = Form(...), rule_id: int = Form(...), maintenance_date: date = Form(...), meter_value: str = Form(""), work_order: str = Form(""), workshop: str = Form(""), description: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    records_url = "/maintenance/records"
    equipment = db.query(Equipment).options(joinedload(Equipment.equipment_type), joinedload(Equipment.equipment_model)).filter(Equipment.id == equipment_id).first()
    if equipment is None: return RedirectResponse(f"{records_url}?error=equipment", status_code=status.HTTP_303_SEE_OTHER)
    rule = get_effective_rule_for_equipment(db, equipment, rule_id)
    if rule is None: return RedirectResponse(f"{records_url}?error=rule_model", status_code=status.HTTP_303_SEE_OTHER)
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
    mapping = db.query(MaintenanceOperationRuleMap).filter(MaintenanceOperationRuleMap.old_rule_id == rule_id).first()
    rec = MaintenanceRecord(equipment_id=equipment_id, rule_id=rule_id, operation_id=mapping.operation_id if mapping else None, maintenance_date=maintenance_date, meter_value=meter, work_order=work_order.strip() or None, workshop=workshop.strip() or None, description=description.strip() or None, status="completed", created_by_id=current_user.id if current_user else None)
    db.add(rec); db.commit()
    return RedirectResponse(f"{records_url}?saved=1", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/maintenance/records/{record_id}/update")
def maintenance_record_update(record_id: int, equipment_id: int = Form(...), rule_id: int = Form(...), maintenance_date: date = Form(...), meter_value: str = Form(""), work_order: str = Form(""), workshop: str = Form(""), description: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    records_url = "/maintenance/records"
    rec = db.query(MaintenanceRecord).filter(MaintenanceRecord.id == record_id).first()
    equipment = db.query(Equipment).options(joinedload(Equipment.equipment_type), joinedload(Equipment.equipment_model)).filter(Equipment.id == equipment_id).first()
    rule = get_effective_rule_for_equipment(db, equipment, rule_id, include_historical=True) if equipment is not None else None
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
    mapping = db.query(MaintenanceOperationRuleMap).filter(MaintenanceOperationRuleMap.old_rule_id == rule_id).first()
    rec.equipment_id = equipment_id; rec.rule_id = rule_id; rec.operation_id = mapping.operation_id if mapping else rec.operation_id; rec.maintenance_date = maintenance_date; rec.meter_value = meter; rec.work_order = work_order.strip() or None; rec.workshop = workshop.strip() or None; rec.description = description.strip() or None
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

# JSON API for the new maintenance library. Legacy HTML routes above remain unchanged.
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

@router.get("/api/maintenance/operations", response_model=list[MaintenanceOperationOut])
def api_operations(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(MaintenanceOperation).order_by(MaintenanceOperation.name, MaintenanceOperation.id).all()

@router.post("/api/maintenance/operations", response_model=MaintenanceOperationOut, status_code=status.HTTP_201_CREATED)
def api_operation_create(payload: MaintenanceOperationCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    data = payload.model_dump()
    if data.get("group_id") is not None and db.get(MaintenanceOperationGroup, data["group_id"]) is None:
        raise HTTPException(status_code=404, detail="مجموعة شروط الصيانة غير موجودة.")
    operation = MaintenanceOperation(**data); db.add(operation)
    try: db.commit(); db.refresh(operation)
    except Exception as exc: db.rollback(); raise HTTPException(status_code=409, detail="تعذر إنشاء عملية الصيانة.") from exc
    return operation

@router.put("/api/maintenance/operations/{operation_id}", response_model=MaintenanceOperationOut)
def api_operation_update(operation_id: int, payload: MaintenanceOperationUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    operation = db.get(MaintenanceOperation, operation_id)
    if operation is None: raise HTTPException(status_code=404, detail="عملية الصيانة غير موجودة.")
    data = payload.model_dump()
    if data.get("group_id") is not None and db.get(MaintenanceOperationGroup, data["group_id"]) is None:
        raise HTTPException(status_code=404, detail="مجموعة شروط الصيانة غير موجودة.")
    for key, value in data.items(): setattr(operation, key, value)
    try: db.commit(); db.refresh(operation)
    except Exception as exc: db.rollback(); raise HTTPException(status_code=409, detail="تعذر تعديل عملية الصيانة.") from exc
    return operation

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

@router.put("/api/maintenance/plans/{plan_id}", response_model=MaintenancePlanOut)
def api_plan_update(plan_id: int, payload: MaintenancePlanUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    plan = db.get(MaintenancePlan, plan_id)
    if plan is None: raise HTTPException(status_code=404, detail="خطة الصيانة غير موجودة.")
    if db.get(EquipmentModel, payload.equipment_model_id) is None: raise HTTPException(status_code=404, detail="طراز العتاد غير موجود.")
    for key, value in payload.model_dump().items(): setattr(plan, key, value)
    try: db.commit(); db.refresh(plan)
    except Exception as exc: db.rollback(); raise HTTPException(status_code=409, detail="تعذر تعديل خطة الصيانة.") from exc
    return plan

@router.get("/api/maintenance/plans/{plan_id}/operations", response_model=list[MaintenancePlanOperationOut])
def api_plan_operations(plan_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if db.get(MaintenancePlan, plan_id) is None: raise HTTPException(status_code=404, detail="خطة الصيانة غير موجودة.")
    return db.query(MaintenancePlanOperation).filter(MaintenancePlanOperation.plan_id == plan_id).order_by(MaintenancePlanOperation.sort_order, MaintenancePlanOperation.id).all()

@router.post("/api/maintenance/plans/{plan_id}/operations", response_model=MaintenancePlanOperationOut, status_code=status.HTTP_201_CREATED)
def api_plan_operation_add(plan_id: int, payload: MaintenancePlanOperationCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if payload.plan_id != plan_id: raise HTTPException(status_code=400, detail="رقم الخطة في الطلب لا يطابق المسار.")
    if db.get(MaintenancePlan, plan_id) is None: raise HTTPException(status_code=404, detail="خطة الصيانة غير موجودة.")
    if db.get(MaintenanceOperation, payload.operation_id) is None: raise HTTPException(status_code=404, detail="عملية الصيانة غير موجودة.")
    link = MaintenancePlanOperation(**payload.model_dump()); db.add(link)
    try: db.commit(); db.refresh(link)
    except Exception as exc: db.rollback(); raise HTTPException(status_code=409, detail="العملية مرتبطة بهذه الخطة مسبقًا أو أن البيانات غير صالحة.") from exc
    return link
