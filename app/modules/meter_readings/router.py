from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from html import escape
from typing import Optional
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from openpyxl.utils.datetime import from_excel
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.core.dependencies import get_current_user
from app.core.templating import get_module_templates
from app.database.session import get_db
from app.modules.equipment import services as equipment_services
from app.modules.equipment_types import services as type_services
from app.modules.meter_readings import services
from app.modules.meter_readings.models import MeterReading
from app.modules.meter_readings.audit_service import add_validation_details, create_operation
from app.modules.meter_readings.excel_reader import load_meter_workbook
from app.modules.users.models import User
router = APIRouter(prefix="/meter-readings", tags=["Meter Readings"])
templates = get_module_templates("app/modules/meter_readings/templates")
def _parse_type_id(value: str | None) -> Optional[int]:
    if value is None or not str(value).strip(): return None
    try: parsed = int(str(value).strip())
    except (ValueError, TypeError): return None
    return parsed if parsed > 0 else None
def _parse_decimal(value):
    if value is None or str(value).strip() == "": raise ValueError("قيمة العداد فارغة")
    text = str(value).strip().replace(" ", "").replace(",", ""); text = text.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")).replace("٫", ".")
    try: return Decimal(text)
    except InvalidOperation as exc: raise ValueError("قيمة العداد غير صحيحة") from exc
def _parse_date(value):
    if isinstance(value, datetime): return value
    if isinstance(value, date): return datetime.combine(value, datetime.min.time())
    if isinstance(value, (int, float)):
        try:
            parsed = from_excel(value); return parsed if isinstance(parsed, datetime) else datetime.combine(parsed, datetime.min.time())
        except Exception: pass
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y"):
        try: return datetime.strptime(text, fmt)
        except ValueError: continue
    raise ValueError("تاريخ القراءة غير صحيح")
def _error_card(message: str, title: str = "خطأ في البيانات"):
    safe = escape(str(message)); return f'<div class="error-card">⚠️ <strong>{escape(title)}</strong><span>{safe}</span></div>'
def _warning_card(message: str): return f'<div class="warning-card">⚠️ <strong>تنبيه</strong><span>{escape(str(message))}</span></div>'
def _equipment_label(equipment):
    if not equipment: return "العتاد غير محدد"
    model = equipment.equipment_model.name if getattr(equipment, "equipment_model", None) else "—"; registration = equipment.registration_number or equipment.asset_code or "—"
    return f"العتاد: {model} — رقم التسجيل: {registration}"
def _registration_context(db: Session, registration):
    raw = str(registration or "").strip()
    if not raw: return "العتاد غير محدد — رقم التسجيل فارغ"
    normalized = services.normalize_registration(raw); equipment = None
    if normalized: equipment = next((x for x in equipment_services.list_equipment(db, limit=10000) if services.normalize_registration(x.registration_number) == normalized), None)
    if equipment: return _equipment_label(equipment)
    return f"رقم التسجيل: {raw} — العتاد غير موجود في النظام"
def _with_input_context(message, db: Session, registration=None, equipment=None, row_number=None):
    prefix = f"الصف {row_number}: " if row_number is not None else ""; context = _equipment_label(equipment) if equipment else _registration_context(db, registration); return f"{prefix}{context}. {message}"
def _annotate_bulk_errors(errors, raw_rows, db):
    annotated = []; import re
    for message in errors:
        match = re.search(r"الصف\s+(\d+)", str(message))
        if not match: annotated.append(message); continue
        row_number = int(match.group(1)); row = {}
        for idx, candidate in enumerate(raw_rows, start=1):
            if isinstance(candidate, dict) and candidate.get("_row_number", idx) == row_number: row = candidate; break
        registration = row.get("registration") if isinstance(row, dict) else None
        if "رقم التسجيل:" in message or "العتاد:" in message: annotated.append(message)
        else: annotated.append(_with_input_context(message, db, registration=registration))
    return annotated
def _page_context(request, db, current_user, page, page_size, search, type_id, unit, sort):
    rows, total, pages, last_update = services.list_latest_rows(db, page=page, page_size=page_size, search=search, type_id=type_id, unit=unit, sort=sort)
    return {"request": request, "user": current_user, "readings": rows, "equipment_options": equipment_services.list_equipment(db, limit=10000), "types": type_services.list_types(db), "total": total, "page": page, "page_size": page_size, "pages": pages, "search": search, "type_id": type_id, "unit": unit, "sort": sort, "last_update": last_update}
def _finish_operation(db: Session, current_user: User, kind: str, filename: str | None, total_rows: int, reading_ids: list[int], rejected_rows: int, errors: list[str], warnings: list[str]):
    op = create_operation(db, kind=kind, user_id=getattr(current_user, "id", None), filename=filename, total_rows=total_rows, reading_ids=reading_ids, rejected_rows=rejected_rows); add_validation_details(db, op.id, getattr(current_user, "id", None), errors=errors, warnings=warnings); db.commit(); return op
@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse, include_in_schema=False)
def meter_readings_page(request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=5, le=100), search: str = Query(""), type_id: str | None = Query(default=None), unit: str = Query(""), sort: str = Query("date_desc"), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    services.cleanup_invalid_readings(db); return templates.TemplateResponse(request=request, name="meter_readings.html", context=_page_context(request, db, current_user, page, page_size, search, _parse_type_id(type_id), unit, sort))
@router.post("/create")
def meter_reading_create(equipment_id: int = Form(...), reading_date: str = Form(...), value: str = Form(...), equipment_status: str | None = Form(None), notes: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    equipment = equipment_services.get_equipment(db, equipment_id); context = _equipment_label(equipment)
    try:
        if not equipment: raise ValueError("العتاد غير موجود")
        date_value = _parse_date(reading_date); meter_value = _parse_decimal(value); unit = equipment.equipment_type.measurement_unit if equipment.equipment_type else "hours"
        reading = services.create_reading(db, equipment_id=equipment_id, odometer=meter_value if unit == "km" else None, hours=meter_value if unit == "hours" else None, reading_date=date_value, notes=notes, equipment_status=equipment_status or "available")
    except ValueError as exc:
        db.rollback(); raise HTTPException(status_code=400, detail=f"{context}. {exc}")
    except SQLAlchemyError:
        db.rollback(); raise HTTPException(status_code=500, detail=f"{context}. تعذر حفظ القراءة بسبب خطأ في قاعدة البيانات.")
    return JSONResponse({"ok": True, "message": "تم حفظ القراءة بنجاح", "reading_id": reading.id})
def _prepare_paste_rows(raw_rows, db):
    valid_rows, parse_errors = [], []
    for index, row in enumerate(raw_rows, start=1):
        if not isinstance(row, dict): parse_errors.append(f"الصف {index}: بيانات غير صحيحة."); continue
        registration = row.get("registration")
        try:
            valid_rows.append({"equipment_model": row.get("model"), "equipment_type": row.get("equipment_type"), "registration": registration, "reading_date": _parse_date(row.get("reading_date")), "km_value": _parse_decimal(row.get("km_value")) if row.get("km_value") not in (None, "") else None, "hours_value": _parse_decimal(row.get("hours_value")) if row.get("hours_value") not in (None, "") else None, "value": _parse_decimal(row.get("value")) if row.get("value") not in (None, "") else None, "equipment_status": row.get("equipment_status"), "_row_number": index})
        except ValueError as exc: parse_errors.append(_with_input_context(str(exc), db, registration=registration, row_number=index))
    return valid_rows, parse_errors
@router.post("/bulk-create")
def meter_readings_bulk_create(payload: dict = Body(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    raw_rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(raw_rows, list): raise HTTPException(status_code=400, detail="بيانات اللصق غير صحيحة.")
    valid_rows, parse_errors = _prepare_paste_rows(raw_rows, db)
    try:
        created, rejected, service_errors, warnings, reading_ids = services.create_bulk_readings(db, valid_rows); errors = parse_errors + _annotate_bulk_errors(service_errors, raw_rows, db); rejected_total = len(raw_rows) - created
        if raw_rows: _finish_operation(db, current_user, "paste", None, len(raw_rows), reading_ids, rejected_total, errors, warnings)
    except SQLAlchemyError:
        db.rollback(); return JSONResponse(status_code=500, content={"created": 0, "skipped": len(raw_rows), "errors": [_error_card("تعذر حفظ القراءات بسبب خطأ في قاعدة البيانات.")]})
    cards = [_error_card(x) for x in errors[:100]] + [_warning_card(x) for x in warnings[:100]]
    return JSONResponse({"ok": not errors, "created": created, "skipped": rejected_total, "errors": cards, "message": "تم حفظ القراءات الصحيحة، مع وجود أخطاء تحتاج للمراجعة." if errors else "تم الحفظ بنجاح."})
def _normalize_header(value):
    if value is None: return ""
    text = str(value).strip().lower()
    for old, new in {"أ": "ا", "إ": "ا", "آ": "ا", "ة": "ه", "ى": "ي", "ـ": "", "ٱ": "ا", "ؤ": "و", "ئ": "ي"}.items(): text = text.replace(old, new)
    return "".join(ch for ch in text if ch.isalnum())
def _header_kind(value):
    text = _normalize_header(value)
    exact = {"الطراز": "equipment_model", "model": "equipment_model", "equipmentmodel": "equipment_model", "نوعالعتاد": "equipment_type", "equipmenttype": "equipment_type", "type": "equipment_type", "رقمالتسجيل": "registration", "التسجيل": "registration", "registration": "registration", "registrationnumber": "registration", "immatriculation": "registration", "matricule": "registration", "reg": "registration", "التاريخ": "date", "تاريخالقراءه": "date", "تاريخالقراءة": "date", "readingdate": "date", "date": "date", "الكيلومترات": "km", "كيلومترات": "km", "الكيلومتر": "km", "كيلومتر": "km", "الكم": "km", "عدادالكم": "km", "عدادالكلم": "km", "عدادالكيلومترات": "km", "عدادكم": "km", "الكلم": "km", "كلم": "km", "كم": "km", "km": "km", "kilometers": "km", "kilometres": "km", "odometer": "km", "الساعات": "hours", "ساعات": "hours", "ساعة": "hours", "عدادالساعات": "hours", "hours": "hours", "hour": "hours", "hourmeter": "hours", "القراءة": "legacy", "قيمهالعداد": "legacy", "قيمةالعداد": "legacy", "reading": "legacy", "value": "legacy", "meter": "legacy", "meterreading": "legacy", "حالهالعداد": "status", "حالةالعداد": "status", "status": "status", "equipmentstatus": "status", "operationalstatus": "status"}
    if text in exact: return exact[text]
    if "طراز" in text or text.endswith("model"): return "equipment_model"
    if "نوع" in text and "عتاد" in text: return "equipment_type"
    if "تسجيل" in text or "registration" in text or "immatriculation" in text or "matricule" in text: return "registration"
    if "تاريخ" in text or text.endswith("date"): return "date"
    if "كيلو" in text or "كلم" in text or "odometer" in text or text.endswith("km"): return "km"
    if "ساع" in text or "hour" in text: return "hours"
    if "حالهالعداد" in text or "حالةالعداد" in text or "status" in text: return "status"
    if "قراء" in text or "value" in text or "meter" in text: return "legacy"
    return None
def _cell(values, idx): return values[idx] if idx is not None and idx < len(values) else None
def _read_excel_rows(file, db):
    workbook = load_meter_workbook(file.file); sheet = workbook.active; rows = list(sheet.iter_rows(values_only=True))
    if not rows: raise ValueError("ملف Excel فارغ.")
    header_info = None
    for row_number, values in enumerate(rows[:20], start=1):
        kinds = {}
        for idx, value in enumerate(values):
            kind = _header_kind(value)
            if kind and kind not in kinds: kinds[kind] = idx
        if ({"equipment_model", "registration", "date", "status"}.issubset(kinds) or {"equipment_type", "registration", "date", "status"}.issubset(kinds)) and ({"km", "hours", "legacy"} & set(kinds)): header_info = (row_number, kinds); break
    if header_info is None: raise ValueError("لم يتم التعرف على أعمدة Excel. يجب أن يحتوي الملف على: الطراز، رقم التسجيل، التاريخ، الكيلومترات أو الساعات، وحالة العداد.")
    header_row, columns = header_info; import_rows, parse_errors, data_row_count = [], [], 0
    for row_number, values in enumerate(rows[header_row:], start=header_row + 1):
        if not any(value is not None and str(value).strip() for value in values): continue
        data_row_count += 1; registration = _cell(values, columns["registration"])
        try:
            import_rows.append({"equipment_model": _cell(values, columns.get("equipment_model")), "equipment_type": _cell(values, columns.get("equipment_type")), "registration": registration, "reading_date": _parse_date(_cell(values, columns["date"])), "km_value": _parse_decimal(_cell(values, columns.get("km"))) if _cell(values, columns.get("km")) not in (None, "") else None, "hours_value": _parse_decimal(_cell(values, columns.get("hours"))) if _cell(values, columns.get("hours")) not in (None, "") else None, "value": _parse_decimal(_cell(values, columns.get("legacy"))) if _cell(values, columns.get("legacy")) not in (None, "") else None, "equipment_status": _cell(values, columns["status"]), "_row_number": row_number})
        except ValueError as exc: parse_errors.append(_with_input_context(str(exc), db, registration=registration, row_number=row_number))
    return import_rows, parse_errors, data_row_count
@router.post("/import-excel")
def meter_readings_import_excel(file: UploadFile = File(...), equipment_status: str | None = Form(None), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    filename = file.filename or ""
    if not filename.lower().endswith(".xlsx"): return JSONResponse(status_code=400, content={"created": 0, "skipped": 0, "errors": [_error_card("الملف يجب أن يكون بصيغة Excel .xlsx.")]})
    try:
        import_rows, parse_errors, data_row_count = _read_excel_rows(file, db); created, rejected, service_errors, warnings, reading_ids = services.create_bulk_readings(db, import_rows); errors = parse_errors + _annotate_bulk_errors(service_errors, import_rows, db); rejected_total = data_row_count - created
        op = _finish_operation(db, current_user, "excel", filename, data_row_count, reading_ids, rejected_total, errors, warnings) if data_row_count else None; cards = [_error_card(x) for x in errors[:100]] + [_warning_card(x) for x in warnings[:100]]
        return JSONResponse({"ok": not errors, "created": created, "skipped": rejected_total, "errors": cards, "message": "تم استيراد القراءات الصحيحة، مع وجود أخطاء تحتاج للمراجعة." if errors else "تم استيراد القراءات بنجاح.", "operation_id": op.id if op else None})
    except ValueError as exc:
        db.rollback(); return JSONResponse(status_code=400, content={"created": 0, "skipped": 0, "errors": [_error_card(str(exc))]})
    except SQLAlchemyError:
        db.rollback(); return JSONResponse(status_code=500, content={"created": 0, "skipped": 0, "errors": [_error_card("تعذر استيراد الملف بسبب خطأ في قاعدة البيانات.")]})
    except Exception as exc:
        db.rollback(); return JSONResponse(status_code=500, content={"created": 0, "skipped": 0, "errors": [_error_card(f"تعذر قراءة ملف Excel: {exc}", "تعذر قراءة ملف Excel")]})
@router.post("/import-excel-preview")
def meter_readings_import_excel_preview(file: UploadFile = File(...), equipment_status: str | None = Form(None), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return meter_readings_import_excel(file, equipment_status, db, current_user)
def _reading_context(db: Session, equipment_id: int, reading_id: int):
    equipment = services.get_equipment_with_readings(db, equipment_id)
    reading = db.query(MeterReading).filter(MeterReading.id == reading_id, MeterReading.equipment_id == equipment_id).first()
    if not equipment: raise HTTPException(status_code=404, detail="العتاد غير موجود")
    if not reading: raise HTTPException(status_code=404, detail=f"{_equipment_label(equipment)}. القراءة غير موجودة")
    return equipment, reading
def _validate_updated_reading(db: Session, equipment_id: int, reading_id: int, reading_date: datetime, value: Decimal, unit: str):
    if reading_date.date() > datetime.now().astimezone().date(): raise ValueError("لا يمكن إدخال قراءة بتاريخ مستقبلي")
    if value < 0: raise ValueError("قيمة العداد لا يمكن أن تكون سالبة")
    for other in services.list_readings(db, equipment_id):
        if other.id == reading_id: continue
        other_value = services._value(other, unit)
        if other_value is None: continue
        other_value = Decimal(other_value)
        if other.reading_date < reading_date and other_value > value:
            raise ValueError(f"القيمة ({value:g}) أقل من القراءة المسجلة بتاريخ {other.reading_date:%d/%m/%Y} ({other_value:g})")
        if other.reading_date > reading_date and other_value < value:
            raise ValueError(f"القيمة ({value:g}) أكبر من القراءة اللاحقة بتاريخ {other.reading_date:%d/%m/%Y} ({other_value:g})")
@router.post("/history/{equipment_id}/update")
def meter_reading_update(equipment_id: int, reading_id: int = Form(...), reading_date: str = Form(...), value: str = Form(...), notes: str = Form(""), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    equipment, reading = _reading_context(db, equipment_id, reading_id); context = _equipment_label(equipment); unit = services._unit(equipment)
    try:
        date_value = _parse_date(reading_date); meter_value = _parse_decimal(value); _validate_updated_reading(db, equipment_id, reading_id, date_value, meter_value, unit)
        if unit == "km": reading.odometer, reading.hours = meter_value, None
        else: reading.hours, reading.odometer = meter_value, None
        reading.reading_date = date_value; reading.notes = (notes or "").strip()[:300] or None; db.flush(); services._refresh_equipment_current(db, equipment, unit); db.commit(); db.refresh(reading)
        return JSONResponse({"ok": True, "message": "تم تعديل القراءة بنجاح", "reading_id": reading.id})
    except ValueError as exc:
        db.rollback(); return JSONResponse(status_code=400, content={"ok": False, "error": f"{context}. {exc}"})
    except SQLAlchemyError:
        db.rollback(); return JSONResponse(status_code=500, content={"ok": False, "error": f"{context}. تعذر تعديل القراءة بسبب خطأ في قاعدة البيانات."})
@router.post("/history/{equipment_id}/delete")
def meter_reading_delete(equipment_id: int, reading_id: int = Form(...), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    equipment, reading = _reading_context(db, equipment_id, reading_id); context = _equipment_label(equipment)
    try:
        db.delete(reading); db.flush(); services._refresh_equipment_current(db, equipment, services._unit(equipment)); db.commit()
        return JSONResponse({"ok": True, "message": "تم حذف القراءة بنجاح"})
    except SQLAlchemyError:
        db.rollback(); return JSONResponse(status_code=500, content={"ok": False, "error": f"{context}. تعذر حذف القراءة بسبب خطأ في قاعدة البيانات."})
@router.get("/history/{equipment_id}", response_class=HTMLResponse)
def meter_history_page(equipment_id: int, request: Request, page: int = Query(1, ge=1), page_size: int = Query(20, ge=5, le=100), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    equipment, rows, total, pages, page = services.history_rows(db, equipment_id, page=page, page_size=page_size)
    if not equipment: raise HTTPException(status_code=404, detail="العتاد غير موجود")
    return templates.TemplateResponse(request=request, name="meter_readings_list.html", context={"request": request, "user": current_user, "equipment": equipment, "rows": rows, "total": total, "pages": pages, "page": page, "page_size": page_size})
