from datetime import date
from decimal import Decimal, InvalidOperation

from io import BytesIO
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session, joinedload

from app.core.dependencies import get_current_user
from app.core.templating import get_module_templates
from app.database.session import get_db
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentModel
from app.modules.fuel import services
from app.modules.fuel.model_rate_import import (
    CONSUMPTION_UNIT_OPTIONS,
    FUEL_TYPE_OPTIONS,
    build_model_rate_template,
    list_models,
    parse_model_rate_workbook,
    save_model_rates,
)
from app.modules.fuel.models import FuelModelConsumptionRate, FuelRecord
from app.modules.users.models import User

router = APIRouter()
templates = get_module_templates("app/modules/fuel/templates")


def dec(value: str):
    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        raise HTTPException(400, "قيمة رقمية غير صالحة")


@router.get("/fuel", response_class=HTMLResponse)
def fuel_page(request: Request, edit: int | None = Query(None), return_to: str = Query("/fuel"), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    records = services.list_records(db)
    enriched, _ = services.enrich_records(db, records)
    models = list_models(db)
    equipment = db.query(Equipment).options(joinedload(Equipment.equipment_model)).order_by(Equipment.registration_number, Equipment.id).all()
    editing_record = db.get(FuelRecord, edit) if edit is not None else None
    if edit is not None and editing_record is None:
        raise HTTPException(404, "سجل التعبئة غير موجود")
    edit_return_to = _fuel_return_path(return_to, editing_record.equipment_id if editing_record else None)
    return templates.TemplateResponse(request=request, name="fuel.html", context={"request": request, "user": current_user, "records": enriched, "equipment": equipment, "models": models, "fuel_types": FUEL_TYPE_OPTIONS, "monthly": services.monthly_summary(db, records), "editing_record": editing_record, "edit_return_to": edit_return_to})


@router.get("/fuel/model-rates", response_class=HTMLResponse)
def fuel_model_rates_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rates = (
        db.query(FuelModelConsumptionRate)
        .options(joinedload(FuelModelConsumptionRate.equipment_model))
        .order_by(FuelModelConsumptionRate.equipment_model_id, FuelModelConsumptionRate.fuel_type)
        .all()
    )
    return templates.TemplateResponse(request=request, name="model_rates.html", context={
        "request": request, "user": current_user, "rates": rates, "models": list_models(db),
        "fuel_types": FUEL_TYPE_OPTIONS, "consumption_units": CONSUMPTION_UNIT_OPTIONS,
        "message": request.query_params.get("message"),
        "error": request.query_params.get("error"),
    })


@router.post("/fuel/model-rates")
def add_fuel_model_rate(
    model_id: int = Form(...), fuel_type: str = Form(...),
    consumption_rate: str = Form(...), measurement_unit: str = Form(...),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    try:
        rate = Decimal(consumption_rate)
        if not rate.is_finite() or rate <= 0:
            raise ValueError("معدل الاستهلاك يجب أن يكون أكبر من صفر.")
        if fuel_type not in FUEL_TYPE_OPTIONS:
            raise ValueError("اختر نوع وقود من القائمة المعتمدة.")
        if measurement_unit not in CONSUMPTION_UNIT_OPTIONS:
            raise ValueError("اختر وحدة قياس من القائمة المعتمدة.")
        if db.get(EquipmentModel, model_id) is None:
            raise ValueError("الطراز المختار غير موجود.")
        existing = db.query(FuelModelConsumptionRate).filter_by(
            equipment_model_id=model_id, fuel_type=fuel_type
        ).one_or_none()
        save_model_rates(db, [{
            "equipment_model_id": model_id,
            "fuel_type": fuel_type,
            "consumption_rate": rate,
            "measurement_unit": measurement_unit,
        }])
        message = "حُدّث معدل الاستهلاك المسجل." if existing else "أُضيف معدل الاستهلاك بنجاح."
        return RedirectResponse("/fuel/model-rates?message=" + quote(message), 303)
    except (InvalidOperation, ValueError) as exc:
        db.rollback()
        return RedirectResponse("/fuel/model-rates?error=" + quote(str(exc)), 303)


@router.get("/fuel/model-rates/template.xlsx")
def fuel_model_rates_template(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    content = build_model_rate_template(list_models(db))
    return StreamingResponse(
        BytesIO(content),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="fuel_model_consumption_rates.xlsx"'},
    )


@router.post("/fuel/model-rates/import")
async def import_fuel_model_rates(file: UploadFile = File(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not (file.filename or "").lower().endswith(".xlsx"):
        return RedirectResponse("/fuel/model-rates?error=" + quote("ارفع ملف Excel بصيغة .xlsx."), 303)
    try:
        rows = parse_model_rate_workbook(await file.read(), list_models(db))
        count = save_model_rates(db, rows)
    except ValueError as exc:
        db.rollback()
        return RedirectResponse("/fuel/model-rates?error=" + quote(str(exc)), 303)
    return RedirectResponse("/fuel/model-rates?message=" + quote(f"تم استيراد أو تحديث {count} معدل استهلاك."), 303)


@router.get("/fuel/equipment", response_class=HTMLResponse)
def fuel_equipment_list_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    equipment_rows = (
        db.query(Equipment)
        .options(joinedload(Equipment.equipment_model).joinedload(EquipmentModel.brand))
        .order_by(Equipment.registration_number, Equipment.id)
        .all()
    )
    records = services.list_records(db)
    _, averages = services.enrich_records(db, records)
    counts: dict[int, int] = {}
    for record in records:
        counts[record.equipment_id] = counts.get(record.equipment_id, 0) + 1
    return templates.TemplateResponse(request=request, name="fuel_equipment.html", context={
        "request": request, "user": current_user, "equipment_rows": equipment_rows,
        "counts": counts, "averages": averages,
    })


@router.post("/fuel")
def create_fuel(equipment_id: int = Form(...), model_id: int = Form(...), fueling_date: date = Form(...), meter_value: str = Form(...), quantity: str = Form(...), fuel_type: str = Form(...), document_number: str = Form(""), station: str = Form(""), notes: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    try:
        equipment = db.query(Equipment).filter(Equipment.id == equipment_id).first()
        if not equipment or equipment.equipment_model_id != model_id:
            raise ValueError("رقم التسجيل لا يتبع الطراز المختار")
        if fuel_type not in FUEL_TYPE_OPTIONS:
            raise ValueError("اختر نوع وقود من القائمة المعتمدة")
        services.add_record(db, {"equipment_id": equipment_id, "fueling_date": fueling_date, "sequence_number": None, "meter_value": dec(meter_value), "quantity": dec(quantity), "fuel_type": fuel_type.strip() or None, "document_number": document_number.strip() or None, "station": station.strip() or None, "notes": notes.strip() or None})
    except ValueError as exc:
        db.rollback(); raise HTTPException(400, str(exc))
    except Exception as exc:
        db.rollback(); raise HTTPException(400, f"تعذر تسجيل التعبئة: {exc}")
    return RedirectResponse("/fuel", 303)


def _fuel_return_path(value: str, equipment_id: int | None) -> str:
    if value == "/fuel":
        return value
    if equipment_id is not None and value == f"/equipment/{equipment_id}/fuel":
        return value
    return "/fuel"


@router.post("/fuel/{record_id:int}/update")
def update_fuel(
    record_id: int,
    fueling_date: date = Form(...),
    meter_value: str = Form(...),
    quantity: str = Form(...),
    fuel_type: str = Form(""),
    document_number: str = Form(""),
    station: str = Form(""),
    notes: str = Form(""),
    return_to: str = Form("/fuel"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    record = db.get(FuelRecord, record_id)
    if record is None:
        raise HTTPException(404, "سجل التعبئة غير موجود")
    destination = _fuel_return_path(return_to, record.equipment_id)
    try:
        if fuel_type and fuel_type not in FUEL_TYPE_OPTIONS:
            raise ValueError("اختر نوع وقود من القائمة المعتمدة")
        services.update_record(db, record_id, {
            "fueling_date": fueling_date,
            "meter_value": dec(meter_value),
            "quantity": dec(quantity),
            "fuel_type": fuel_type.strip() or None,
            "document_number": document_number.strip() or None,
            "station": station.strip() or None,
            "notes": notes.strip() or None,
        })
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))
    except Exception as exc:
        db.rollback()
        raise HTTPException(400, f"تعذر تعديل سجل التعبئة: {exc}")
    return RedirectResponse(destination, 303)


@router.post("/fuel/{record_id:int}/delete")
def delete_fuel(
    record_id: int,
    return_to: str = Form("/fuel"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    record = db.get(FuelRecord, record_id)
    if record is None:
        raise HTTPException(404, "سجل التعبئة غير موجود")
    destination = _fuel_return_path(return_to, record.equipment_id)
    try:
        services.delete_records(db, [record_id])
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))
    return RedirectResponse(destination, 303)


@router.post("/fuel/delete-selected")
def delete_selected_fuel(
    record_ids: list[int] = Form(...),
    return_to: str = Form("/fuel"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    records = db.query(FuelRecord).filter(FuelRecord.id.in_(set(record_ids))).all()
    equipment_ids = {record.equipment_id for record in records}
    destination = "/fuel"
    if return_to == "/fuel":
        destination = return_to
    elif len(equipment_ids) == 1 and return_to == f"/equipment/{next(iter(equipment_ids))}/fuel":
        destination = return_to
    try:
        services.delete_records(db, record_ids)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))
    return RedirectResponse(destination, 303)


@router.get("/equipment/{equipment_id}/fuel", response_class=HTMLResponse)
def equipment_fuel_page(request: Request, equipment_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    equipment = db.query(Equipment).options(joinedload(Equipment.equipment_model).joinedload(EquipmentModel.brand)).filter(Equipment.id == equipment_id).first()
    if not equipment:
        raise HTTPException(404, "العتاد غير موجود")
    records = db.query(FuelRecord).options(joinedload(FuelRecord.equipment)).filter(FuelRecord.equipment_id == equipment_id).order_by(FuelRecord.fueling_date.desc(), FuelRecord.id.desc()).all()
    enriched, averages = services.enrich_records(db, records)
    return templates.TemplateResponse(request=request, name="equipment_fuel.html", context={"request": request, "user": current_user, "equipment": equipment, "records": enriched, "average": averages.get(equipment_id)})
