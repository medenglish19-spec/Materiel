from typing import Optional
from datetime import datetime
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.permissions import Role, require_role
from app.core.templating import get_module_templates
from app.database.session import get_db
from app.modules.equipment import services
from app.modules.equipment.schemas import EquipmentCreate, EquipmentOut, EquipmentUpdate
from app.modules.equipment_types import services as type_services
from app.modules.users.models import User
from app.modules.meter_readings import services as meter_services
from app.modules.meter_readings.models import MeterReading
from app.modules.meter_readings.audit import MeterReadingChange, utc_now

router = APIRouter()
templates = get_module_templates("app/modules/equipment/templates")


@router.get("/equipment", response_class=HTMLResponse)
def equipment_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = services.list_equipment(db)
    types = type_services.list_types(db)
    return templates.TemplateResponse(
        "equipment_list.html",
        {"request": request, "items": items, "types": types, "user": current_user},
    )


@router.get("/equipment/fleet-status", response_class=HTMLResponse)
def equipment_fleet_status_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """عرض تركيبة الحضيرة ومؤشرات الاحتياج التشغيلي دون التأثير على بيانات العتاد."""
    from collections import defaultdict
    from app.modules.equipment_types.models import EquipmentCategory, EquipmentType, EquipmentModel

    categories = db.query(EquipmentCategory).order_by(EquipmentCategory.sort_order, EquipmentCategory.name).all()
    category_map = {
        c.id: {"category_id": c.id, "category_name": c.name, "total": 0, "ready": 0,
               "in_mission": 0, "in_maintenance": 0, "in_external_workshop": 0,
               "unavailable": 0, "potential_need": 0}
        for c in categories
    }

    type_map = {}
    model_map = {}
    rows = (
        db.query(Equipment)
        .join(EquipmentType, Equipment.equipment_type_id == EquipmentType.id)
        .outerjoin(EquipmentCategory, EquipmentType.category_id == EquipmentCategory.id)
        .outerjoin(EquipmentModel, Equipment.equipment_model_id == EquipmentModel.id)
        .with_entities(
            Equipment.equipment_type_id,
            Equipment.equipment_model_id,
            Equipment.operational_status,
            Equipment.technical_condition,
            EquipmentType.name,
            EquipmentModel.name,
            EquipmentType.category_id,
            EquipmentCategory.name,
        )
        .all()
    )

    for type_id, model_id, op_status, tech_condition, type_name, model_name, category_id, category_name in rows:
        category_name = category_name or "غير مصنف"
        if category_id not in category_map:
            category_map[category_id] = {
                "category_id": category_id, "category_name": category_name, "total": 0,
                "ready": 0, "in_mission": 0, "in_maintenance": 0,
                "in_external_workshop": 0, "unavailable": 0, "potential_need": 0,
            }
        cat = category_map[category_id]
        cat["total"] += 1
        if op_status in cat:
            cat[op_status] += 1
        if op_status == "available" and tech_condition == "ready":
            cat["ready"] += 1
        if op_status != "available" or tech_condition != "ready":
            cat["potential_need"] += 1

        tkey = type_id
        t = type_map.setdefault(tkey, {
            "category_id": category_id, "category_name": category_name,
            "type_name": type_name, "total": 0, "ready": 0,
            "not_ready": 0, "in_maintenance": 0, "unavailable": 0,
        })
        t["total"] += 1
        if op_status == "available" and tech_condition == "ready":
            t["ready"] += 1
        else:
            t["not_ready"] += 1
        if op_status == "in_maintenance":
            t["in_maintenance"] += 1
        if op_status == "unavailable":
            t["unavailable"] += 1

        if model_id is not None:
            mkey = model_id
            m = model_map.setdefault(mkey, {
                "category_id": category_id, "category_name": category_name,
                "type_name": type_name, "model_name": model_name,
                "total": 0, "ready": 0, "not_ready": 0,
                "in_maintenance": 0, "unavailable": 0,
            })
            m["total"] += 1
            if op_status == "available" and tech_condition == "ready":
                m["ready"] += 1
            else:
                m["not_ready"] += 1
            if op_status == "in_maintenance":
                m["in_maintenance"] += 1
            if op_status == "unavailable":
                m["unavailable"] += 1

    category_rows = sorted(category_map.values(), key=lambda x: x["category_name"])
    type_rows = sorted(type_map.values(), key=lambda x: (x["category_name"], x["type_name"]))
    model_rows = sorted(model_map.values(), key=lambda x: (x["category_name"], x["type_name"], x["model_name"] or ""))

    total = len(rows)
    ready = sum(1 for row in rows if row[2] == "available" and row[3] == "ready")
    potential_need = sum(1 for row in rows if row[2] != "available" or row[3] != "ready")
    summary = {"total": total, "ready": ready, "not_ready": total - ready, "potential_need": potential_need}

    return templates.TemplateResponse(
        "equipment_fleet_status.html",
        {
            "request": request,
            "user": current_user,
            "summary": summary,
            "categories": category_rows,
            "types": type_rows,
            "models": model_rows,
        },
    )


@router.get("/equipment/{equipment_id}", response_class=HTMLResponse)
def equipment_detail_page(
    equipment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = services.get_equipment(db, equipment_id)
    if not item:
        raise HTTPException(status_code=404, detail="العتاد غير موجود")
    return templates.TemplateResponse(
        "equipment_detail.html",
        {"request": request, "item": item, "user": current_user},
    )


@router.get("/equipment/{equipment_id}/edit", response_class=HTMLResponse)
def equipment_edit_page(
    equipment_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = services.get_equipment(db, equipment_id)
    if not item:
        raise HTTPException(status_code=404, detail="العتاد غير موجود")
    types = type_services.list_types(db)
    return templates.TemplateResponse(
        "equipment_edit.html",
        {"request": request, "item": item, "types": types, "user": current_user},
    )


@router.post("/equipment/create")
def equipment_create_form(
    request: Request,
    equipment_type_id: int = Form(...),
    equipment_model_id: Optional[str] = Form(None),
    acquisition_document: str = Form(""),
    registration_number: str = Form(""),
    vin: str = Form(""),
    current_odometer: str = Form("0"),
    current_hours: str = Form("0"),
    technical_condition: str = Form("ready"),
    operational_status: str = Form("available"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        services.create_equipment(
            db,
            EquipmentCreate(
                equipment_type_id=equipment_type_id,
                equipment_model_id=int(equipment_model_id) if equipment_model_id else None,
                acquisition_document=acquisition_document or None,
                registration_number=registration_number or None,
                vin=vin or None,
                current_odometer=current_odometer or 0,
                current_hours=current_hours or 0,
                technical_condition=technical_condition,
                operational_status=operational_status,
            ),
            user_id=current_user.id,
        )
    except ValueError:
        pass
    return RedirectResponse(url="/equipment", status_code=status.HTTP_302_FOUND)


@router.post("/equipment/{equipment_id}/edit")
def equipment_edit_form(
    equipment_id: int,
    equipment_type_id: int = Form(...),
    equipment_model_id: Optional[str] = Form(None),
    acquisition_document: str = Form(""),
    registration_number: str = Form(""),
    vin: str = Form(""),
    acquisition_date: str = Form(""),
    technical_condition: str = Form("ready"),
    operational_status: str = Form("available"),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = services.get_equipment(db, equipment_id)
    if not item:
        raise HTTPException(status_code=404, detail="العتاد غير موجود")

    try:
        date_value = datetime.strptime(acquisition_date, "%Y-%m-%d").date() if acquisition_date.strip() else None
        model_id = int(equipment_model_id) if equipment_model_id else None
        services.update_equipment(
            db,
            item,
            EquipmentUpdate(
                equipment_type_id=equipment_type_id,
                equipment_model_id=model_id,
                acquisition_document=acquisition_document or None,
                registration_number=registration_number or None,
                vin=vin or None,
                acquisition_date=date_value,
                technical_condition=technical_condition,
                operational_status=operational_status,
                notes=notes or None,
            ),
            user_id=current_user.id,
        )
    except (ValueError, InvalidOperation) as exc:
        raise HTTPException(status_code=400, detail=str(exc) or "بيانات التعديل غير صحيحة")

    return RedirectResponse(url=f"/equipment/{equipment_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/equipment/{equipment_id}/delete")
def equipment_delete_form(
    equipment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(Role.ADMIN)),
):
    item = services.get_equipment(db, equipment_id)
    if item:
        services.delete_equipment(db, item)
    return RedirectResponse(url="/equipment", status_code=status.HTTP_302_FOUND)


@router.get("/equipment/{equipment_id}/meters", response_class=HTMLResponse)
def equipment_meters_page(
    equipment_id: int,
    request: Request,
    page: int = 1,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item, readings, total_readings, total_pages, current_page = meter_services.history_rows(
        db, equipment_id, page=page, page_size=20
    )
    if not item:
        raise HTTPException(status_code=404, detail="العتاد غير موجود")
    return templates.TemplateResponse(
        "equipment_meters.html",
        {
            "request": request,
            "item": item,
            "readings": readings,
            "total_readings": total_readings,
            "total_pages": total_pages,
            "current_page": current_page,
            "user": current_user,
        },
    )


@router.post("/equipment/{equipment_id}/meters/create")
def equipment_meter_create(
    equipment_id: int,
    reading_date: str = Form(...),
    odometer: str = Form(""),
    hours: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = services.get_equipment(db, equipment_id)
    if not item:
        raise HTTPException(status_code=404, detail="العتاد غير موجود")
    try:
        date_value = datetime.strptime(reading_date, "%Y-%m-%d")
        odometer_value = Decimal(odometer) if odometer.strip() else None
        hours_value = Decimal(hours) if hours.strip() else None
    except (ValueError, InvalidOperation):
        raise HTTPException(status_code=400, detail="تاريخ أو قيمة عداد غير صحيحة")
    if odometer_value is None and hours_value is None:
        raise HTTPException(status_code=400, detail="يجب إدخال قراءة الكيلومترات أو قراءة الساعات")
    try:
        meter_services.create_reading(
            db, equipment_id=equipment_id, odometer=odometer_value, hours=hours_value,
            reading_date=date_value, notes=notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return RedirectResponse(url=f"/equipment/{equipment_id}/meters", status_code=status.HTTP_302_FOUND)


@router.post("/equipment/{equipment_id}/meters/{reading_id}/update")
def equipment_meter_update(
    equipment_id: int,
    reading_id: int,
    reading_date: str = Form(...),
    odometer: str = Form(""),
    hours: str = Form(""),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = services.get_equipment(db, equipment_id)
    reading = db.query(MeterReading).filter(
        MeterReading.id == reading_id,
        MeterReading.equipment_id == equipment_id,
    ).first()
    if not item or not reading:
        raise HTTPException(status_code=404, detail="القراءة غير موجودة")

    try:
        date_value = datetime.strptime(reading_date, "%Y-%m-%d")
        unit = meter_services._unit(item)
        raw_value = odometer if unit == "km" else hours
        if not raw_value.strip():
            raise ValueError("يجب إدخال قيمة العداد")
        value = meter_services._parse_decimal(raw_value)
    except (ValueError, InvalidOperation) as exc:
        raise HTTPException(status_code=400, detail=str(exc) or "تاريخ أو قيمة عداد غير صحيحة")

    if value < 0:
        raise HTTPException(status_code=400, detail="قيمة العداد لا يمكن أن تكون سالبة")
    if date_value.date() > datetime.now().date():
        raise HTTPException(status_code=400, detail="لا يمكن إدخال قراءة بتاريخ مستقبلي")

    for existing in meter_services.list_readings(db, equipment_id):
        if existing.id == reading.id:
            continue
        existing_value = meter_services._value(existing, unit)
        if existing_value is None:
            continue
        existing_value = Decimal(existing_value)
        if existing.reading_date < date_value and existing_value > value:
            raise HTTPException(status_code=400, detail="قيمة القراءة الجديدة أقل من قراءة لاحقة مسجلة")
        if existing.reading_date > date_value and existing_value < value:
            raise HTTPException(status_code=400, detail="قيمة القراءة الجديدة أكبر من قراءة لاحقة مسجلة")

    reading.reading_date = date_value
    reading.odometer = value if unit == "km" else None
    reading.hours = value if unit == "hours" else None
    reading.notes = (notes or "").strip()[:300] or None
    meter_services._refresh_equipment_current(db, item, unit)
    db.commit()
    return RedirectResponse(url=f"/equipment/{equipment_id}/meters", status_code=status.HTTP_302_FOUND)


@router.post("/equipment/{equipment_id}/meters/{reading_id}/delete")
def equipment_meter_delete(
    equipment_id: int,
    reading_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = services.get_equipment(db, equipment_id)
    reading = db.query(MeterReading).filter(
        MeterReading.id == reading_id,
        MeterReading.equipment_id == equipment_id,
    ).first()
    if not item or not reading:
        raise HTTPException(status_code=404, detail="القراءة غير موجودة")

    unit = meter_services._unit(item)
    old_value = meter_services._value(reading, unit)
    db.add(MeterReadingChange(
        reading_id=reading.id,
        equipment_id=equipment_id,
        changed_at=utc_now(),
        action="delete",
        source=reading.source or "manual",
        reading_date=reading.reading_date,
        unit=unit,
        old_value=old_value,
        new_value=None,
        actor_id=current_user.id,
        details="حذف قراءة مسجلة.",
    ))
    db.delete(reading)
    db.flush()
    meter_services._refresh_equipment_current(db, item, unit)
    db.commit()
    return RedirectResponse(url=f"/equipment/{equipment_id}/meters", status_code=status.HTTP_302_FOUND)


@router.get("/api/equipment", response_model=list[EquipmentOut])
def api_list_equipment(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return services.list_equipment(db)


@router.get("/api/equipment/{equipment_id}", response_model=EquipmentOut)
def api_get_equipment(
    equipment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = services.get_equipment(db, equipment_id)
    if not item:
        raise HTTPException(status_code=404, detail="العتاد غير موجود")
    return item
