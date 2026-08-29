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
    items = services.list_equipment(db)
    categories = {}
    for item in items:
        category = item.equipment_type.category if item.equipment_type else None
        category_key = category.id if category else 0
        category_name = category.name if category else "غير مصنف"
        bucket = categories.setdefault(category_key, {
            "name": category_name,
            "total": 0,
            "ready": 0,
            "not_ready": 0,
            "in_maintenance": 0,
            "unavailable": 0,
            "types": {},
        })
        bucket["total"] += 1
        ready = item.technical_condition == "ready" and item.operational_status == "available"
        if ready:
            bucket["ready"] += 1
        else:
            bucket["not_ready"] += 1
        if item.operational_status in ("in_maintenance", "in_external_workshop"):
            bucket["in_maintenance"] += 1
        if item.operational_status == "unavailable" or item.technical_condition == "broken":
            bucket["unavailable"] += 1

        type_bucket = bucket["types"].setdefault(item.equipment_type_id, {
            "name": item.equipment_type.name if item.equipment_type else "غير معروف",
            "total": 0,
            "ready": 0,
            "not_ready": 0,
            "models": {},
        })
        type_bucket["total"] += 1
        if ready:
            type_bucket["ready"] += 1
        else:
            type_bucket["not_ready"] += 1

        model_key = item.equipment_model_id or 0
        model_bucket = type_bucket["models"].setdefault(model_key, {
            "name": item.equipment_model.name if item.equipment_model else "بدون طراز",
            "total": 0,
            "ready": 0,
            "not_ready": 0,
        })
        model_bucket["total"] += 1
        if ready:
            model_bucket["ready"] += 1
        else:
            model_bucket["not_ready"] += 1

    category_rows = sorted(
        categories.values(),
        key=lambda x: x["name"],
    )
    for row in category_rows:
        row["types"] = sorted(row["types"].values(), key=lambda x: x["name"])
        for type_row in row["types"]:
            type_row["models"] = sorted(type_row["models"].values(), key=lambda x: x["name"])

    totals = {
        "total": len(items),
        "ready": sum(1 for x in items if x.technical_condition == "ready" and x.operational_status == "available"),
        "not_ready": sum(1 for x in items if not (x.technical_condition == "ready" and x.operational_status == "available")),
        "in_maintenance": sum(1 for x in items if x.operational_status in ("in_maintenance", "in_external_workshop")),
        "unavailable": sum(1 for x in items if x.operational_status == "unavailable" or x.technical_condition == "broken"),
    }
    return templates.TemplateResponse(
        "fleet_status.html",
        {
            "request": request,
            "categories": category_rows,
            "totals": totals,
            "user": current_user,
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
