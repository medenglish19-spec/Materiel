from __future__ import annotations
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional, Iterable
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentType
from app.modules.meter_readings.models import MeterReading

def _unit(equipment: Equipment) -> str:
    return equipment.equipment_type.measurement_unit if equipment.equipment_type else "hours"
def _value(reading: MeterReading | None, unit: str):
    if reading is None: return None
    return reading.odometer if unit == "km" else reading.hours
def _fmt(value) -> str:
    if value is None: return "—"
    value = Decimal(value)
    if value == value.to_integral_value(): return f"{int(value):,}"
    return f"{value:,.1f}"
def _fmt_difference(value) -> str:
    if value is None: return "—"
    value = Decimal(value)
    if value < 0: return "غير صالح"
    if value == value.to_integral_value(): return f"+{int(value):,}"
    return f"+{value:,.1f}"
def _source_label(value: str | None) -> str:
    return {
        "manual": "إدخال يدوي", "import": "استيراد Excel", "paste": "لصق جماعي",
        "fuel": "الوقود", "fault": "العطل", "repair": "الإصلاح",
        "maintenance": "الصيانة", "mission_departure": "المهمة — الانطلاق",
        "mission_return": "المهمة — العودة", "tire_movement": "حركة إطار",
        "battery_movement": "حركة بطارية", "equipment_create": "إضافة العتاد",
    }.get(value or "", value or "غير محدد")
def _difference(current: MeterReading, previous: MeterReading | None, unit: str):
    current_value = _value(current, unit); previous_value = _value(previous, unit)
    if current_value is None or previous_value is None: return None
    return Decimal(current_value) - Decimal(previous_value)
def _equipment_status_label(equipment: Equipment) -> tuple[str, str]:
    value = str(equipment.operational_status or "available").strip().lower()
    if value in {"unavailable", "not_working", "not-working", "stopped", "out_of_service", "out-of-service"}: return "لا يعمل", "danger"
    return "يعمل", "success"
def _reading_status_label(reading: MeterReading | None, fallback_equipment: Equipment | None = None) -> tuple[str, str]:
    value = str((reading.equipment_status if reading is not None else None) or (fallback_equipment.operational_status if fallback_equipment is not None else "available")).strip().lower()
    if value in {"unavailable", "not_working", "not-working", "stopped", "out_of_service", "out-of-service"}: return "لا يعمل", "danger"
    return "يعمل", "success"
def normalize_equipment_status(value) -> str:
    text = str(value or "").strip().lower()
    if text in {"لا يعمل", "لايعمل", "غير متاح", "غيرمتاح", "unavailable", "not_working", "not-working", "stopped", "out_of_service", "out-of-service"}: return "unavailable"
    return "available"
def parse_equipment_status(value) -> str:
    text = str(value or "").strip().lower()
    if text in {"يعمل", "يشتغل", "متاح", "available", "working", "on"}: return "available"
    if text in {"لا يعمل", "لايعمل", "غير متاح", "غيرمتاح", "unavailable", "not_working", "not-working", "stopped", "out_of_service", "out-of-service", "off"}: return "unavailable"
    raise ValueError("حالة العداد غير صحيحة؛ يجب أن تكون «يعمل» أو «لا يعمل».")
def normalize_registration(value) -> str:
    if value is None: return ""
    text = str(value).strip().upper()
    if text.endswith(".0") and text[:-2].isdigit(): text = text[:-2]
    return "".join(ch for ch in text if ch.isalnum())
def _parse_decimal(value) -> Decimal:
    text = str(value).strip().replace(" ", "").replace(",", "")
    text = text.translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")).replace("٫", ".")
    try: return Decimal(text)
    except (InvalidOperation, ValueError) as exc: raise ValueError("قيمة العداد غير صحيحة") from exc
def list_readings(db: Session, equipment_id: int) -> list[MeterReading]:
    return db.query(MeterReading).filter(MeterReading.equipment_id == equipment_id).order_by(MeterReading.reading_date.asc(), MeterReading.id.asc()).all()
def _validate_reading_position(db: Session, equipment_id: int, reading_date: datetime, value: Decimal, unit: str, exclude_reading_id: int | None = None):
    observations = _meter_observations(db, equipment_id, unit, exclude_reading_id)
    day = reading_date.date()
    for other_day, other_value, source in observations:
        if other_day == day:
            if other_value == value:
                raise ValueError(f"القراءة ({value:g}) مكررة في {day:%d/%m/%Y}؛ مصدر القراءة المسجلة: {source}.")
            raise ValueError(f"تعارض في قراءة العداد بتاريخ {day:%d/%m/%Y}: القيمة المدخلة ({value:g}) تختلف عن ({other_value:g}) المسجلة من مصدر «{source}».")
        if other_day < day and other_value > value:
            raise ValueError(f"لا يمكن حفظ القراءة بتاريخ {day:%d/%m/%Y}: قيمتها ({value:g}) أقل من القراءة المسجلة بتاريخ {other_day:%d/%m/%Y} ({other_value:g}) من مصدر «{source}».")
        if other_day > day and other_value < value:
            raise ValueError(f"لا يمكن إدخال قراءة بتاريخ {day:%d/%m/%Y}: قيمتها ({value:g}) أكبر من القراءة اللاحقة بتاريخ {other_day:%d/%m/%Y} ({other_value:g}) من مصدر «{source}».")


def _meter_observations(db: Session, equipment_id: int, unit: str, exclude_reading_id: int | None = None, exclude_reference: str | None = None):
    """Read the central meter ledger; domain modules are never chronology sources."""
    observations = []
    column = MeterReading.odometer if unit == "km" else MeterReading.hours
    query = db.query(MeterReading.id, MeterReading.reading_date, column, MeterReading.source).filter(
        MeterReading.equipment_id == equipment_id, column.isnot(None)
    )
    if exclude_reading_id is not None:
        query = query.filter(MeterReading.id != exclude_reading_id)
    if exclude_reference is not None:
        query = query.filter(or_(MeterReading.source_reference.is_(None), MeterReading.source_reference != exclude_reference))
    for _identifier, day, value, source in query:
        observations.append((day.date(), Decimal(str(value)), _source_label(source)))

    return observations


def validate_meter_observation(db: Session, equipment_id: int, event_date, value, unit: str, source: str, source_reference: str | None = None):
    """Apply central meter chronology rules to observations entered by another module."""
    if value is None:
        return
    value = Decimal(str(value))
    if value < 0:
        raise ValueError("لا يمكن أن تكون قراءة العداد سالبة")
    day = event_date.date() if hasattr(event_date, "date") else event_date
    for other_day, other_value, other_source in _meter_observations(db, equipment_id, unit, exclude_reference=source_reference):
        if other_day == day:
            if other_value == value:
                raise ValueError(f"قراءة العداد ({value:g}) مسجلة مسبقًا بتاريخ {day:%d/%m/%Y} من مصدر «{other_source}».")
            raise ValueError(f"تعارض قراءة العداد في نفس التاريخ ({day:%d/%m/%Y}): قيمة «{source}» ({value:g}) تختلف عن ({other_value:g}) من مصدر «{other_source}».")
        if other_day < day and other_value > value:
            raise ValueError(f"قراءة «{source}» ({value:g}) أقل من القراءة الأقدم ({other_value:g}) من مصدر «{other_source}».")
        if other_day > day and other_value < value:
            raise ValueError(f"قراءة «{source}» ({value:g}) أكبر من قراءة لاحقة ({other_value:g}) من مصدر «{other_source}».")
def _refresh_equipment_current(db: Session, equipment: Equipment, unit: str):
    db.flush()
    value_column = MeterReading.odometer if unit == "km" else MeterReading.hours
    latest_value = db.query(value_column).filter(
        MeterReading.equipment_id == equipment.id,
        value_column.isnot(None),
        MeterReading.reading_date <= datetime.combine(date.today(), datetime.max.time()),
    ).order_by(MeterReading.reading_date.desc(), MeterReading.id.desc()).limit(1).scalar()
    if unit == "km": equipment.current_odometer = latest_value
    else: equipment.current_hours = latest_value


def sync_current_meter(db: Session, equipment_id: int):
    equipment = get_equipment_with_readings(db, equipment_id)
    if equipment:
        _refresh_equipment_current(db, equipment, _unit(equipment))
def cleanup_invalid_readings(db: Session):
    today = datetime.now(timezone.utc).date(); cutoff = datetime.combine(today, datetime.max.time())
    invalid = db.query(MeterReading).filter(MeterReading.reading_date > cutoff).all(); invalid += db.query(MeterReading).filter((MeterReading.odometer < 0) | (MeterReading.hours < 0)).all()
    unique = {item.id: item for item in invalid}
    if not unique: return 0
    equipment_ids = {item.equipment_id for item in unique.values()}
    for item in unique.values(): db.delete(item)
    db.flush()
    for equipment_id in equipment_ids:
        equipment = get_equipment_with_readings(db, equipment_id)
        if equipment: _refresh_equipment_current(db, equipment, _unit(equipment))
    db.commit(); return len(unique)
def list_latest_rows(db: Session, page: int = 1, page_size: int = 10, search: str = "", type_id: Optional[int] = None, unit: str = "", sort: str = "date_desc"):
    page = max(1, page); page_size = min(max(1, page_size), 100)
    latest_dates = db.query(MeterReading.equipment_id.label("equipment_id"), func.max(MeterReading.reading_date).label("latest_date")).group_by(MeterReading.equipment_id).subquery()
    query = db.query(Equipment, latest_dates.c.latest_date).join(EquipmentType, Equipment.equipment_type_id == EquipmentType.id).outerjoin(latest_dates, latest_dates.c.equipment_id == Equipment.id).options(joinedload(Equipment.equipment_type), joinedload(Equipment.equipment_model))
    if type_id: query = query.filter(Equipment.equipment_type_id == type_id)
    if unit in {"km", "hours"}: query = query.filter(EquipmentType.measurement_unit == unit)
    if search.strip():
        term = f"%{search.strip()}%"; query = query.filter(or_(Equipment.asset_code.ilike(term), Equipment.registration_number.ilike(term), Equipment.vin.ilike(term), EquipmentType.name.ilike(term)))
    total = query.count()
    if sort == "registration": query = query.order_by(Equipment.registration_number.asc(), Equipment.id.asc())
    elif sort == "date_asc": query = query.order_by(latest_dates.c.latest_date.asc(), Equipment.id.asc())
    else: query = query.order_by(latest_dates.c.latest_date.desc(), Equipment.id.asc())
    selected = query.offset((page - 1) * page_size).limit(page_size).all(); equipment_ids = [equipment.id for equipment, _ in selected]; history = {equipment_id: [] for equipment_id in equipment_ids}
    if equipment_ids:
        readings = db.query(MeterReading).filter(MeterReading.equipment_id.in_(equipment_ids)).order_by(MeterReading.equipment_id.asc(), MeterReading.reading_date.desc(), MeterReading.id.desc()).all()
        for reading in readings:
            bucket = history[reading.equipment_id]
            if len(bucket) < 2: bucket.append(reading)
    rows = []
    for number, (equipment, _) in enumerate(selected, start=(page - 1) * page_size + 1):
        unit_code = _unit(equipment); latest = history[equipment.id][0] if history[equipment.id] else None; previous = history[equipment.id][1] if len(history[equipment.id]) > 1 else None; difference = _difference(latest, previous, unit_code) if latest else None; equipment_status, status_class = _reading_status_label(latest, equipment)
        rows.append({"number": number, "equipment_id": equipment.id, "model": equipment.equipment_model.name if equipment.equipment_model else "—", "type_name": equipment.equipment_type.name if equipment.equipment_type else "—", "registration": equipment.registration_number or equipment.asset_code or "—", "location": "—", "unit": "كم" if unit_code == "km" else "ساعة عمل", "unit_code": unit_code, "date": latest.reading_date.strftime("%d/%m/%Y") if latest else "—", "reading": _fmt(_value(latest, unit_code)), "difference": _fmt_difference(difference), "note": latest.notes if latest and latest.notes else "—", "status": equipment_status, "status_class": status_class, "source": _source_label(latest.source) if latest else "—"})
    last_update = db.query(func.max(MeterReading.reading_date)).scalar(); last_update_text = last_update.strftime("%d/%m/%Y") if last_update else "—"; pages = (total + page_size - 1) // page_size if total else 1
    return rows, total, pages, last_update_text
def get_equipment_with_readings(db: Session, equipment_id: int):
    return db.query(Equipment).options(joinedload(Equipment.equipment_type), joinedload(Equipment.equipment_model)).filter(Equipment.id == equipment_id).first()
def history_rows(db: Session, equipment_id: int, page: int = 1, page_size: int = 20):
    equipment = get_equipment_with_readings(db, equipment_id)
    if not equipment: return None, [], 0, 1, 1
    page = max(1, page); page_size = min(max(1, page_size), 100); unit_code = _unit(equipment)
    ordered = db.query(MeterReading.id.label("id"), MeterReading.reading_date.label("reading_date"), MeterReading.odometer.label("odometer"), MeterReading.hours.label("hours"), MeterReading.equipment_status.label("equipment_status"), MeterReading.notes.label("notes"), MeterReading.source.label("source"), func.lag(MeterReading.odometer).over(partition_by=MeterReading.equipment_id, order_by=(MeterReading.reading_date.desc(), MeterReading.id.desc())).label("previous_odometer"), func.lag(MeterReading.hours).over(partition_by=MeterReading.equipment_id, order_by=(MeterReading.reading_date.desc(), MeterReading.id.desc())).label("previous_hours")).filter(MeterReading.equipment_id == equipment_id).subquery()
    total = db.query(func.count()).select_from(ordered).scalar() or 0; pages = max(1, (total + page_size - 1) // page_size); page = min(page, pages); rows_data = db.query(ordered).order_by(ordered.c.reading_date.desc(), ordered.c.id.desc()).offset((page - 1) * page_size).limit(page_size).all(); rows = []
    for number, row in enumerate(rows_data, start=(page - 1) * page_size + 1):
        current_value = row.odometer if unit_code == "km" else row.hours; previous_value = row.previous_odometer if unit_code == "km" else row.previous_hours; difference = Decimal(current_value) - Decimal(previous_value) if current_value is not None and previous_value is not None else None; status, status_class = _reading_status_label(row, equipment)
        rows.append({"number": number, "id": row.id, "date": row.reading_date.strftime("%d/%m/%Y"), "odometer": _fmt(row.odometer), "hours": _fmt(row.hours), "reading": _fmt(current_value), "difference": _fmt_difference(difference), "note": row.notes or "—", "source": _source_label(row.source), "status": status, "status_class": status_class, "unit": "كم" if unit_code == "km" else "ساعة عمل"})
    return equipment, rows, total, pages, page
def _ensure_not_duplicate_reading(db: Session, equipment_id: int, reading_date: datetime, value: Decimal, unit: str, exclude_id: int | None = None):
    for existing in list_readings(db, equipment_id):
        if exclude_id is not None and existing.id == exclude_id: continue
        existing_value = _value(existing, unit)
        if existing_value is None: continue
        if existing.reading_date.date() == reading_date.date() and Decimal(existing_value) == value:
            raise ValueError(f"لا يمكن إضافة نفس قراءة العداد مرتين للعتاد في تاريخ {reading_date:%d/%m/%Y}: القيمة ({value:g}) موجودة مسبقًا. لم يتم حفظ قراءة مكررة.")
def create_reading(db: Session, equipment_id: int, odometer=None, hours=None, reading_date: datetime | None = None, notes: str | None = None, equipment_status: str | None = None) -> MeterReading:
    equipment = get_equipment_with_readings(db, equipment_id)
    if not equipment: raise ValueError("العتاد غير موجود")
    unit_code = _unit(equipment); value = odometer if unit_code == "km" else hours
    if value is None: raise ValueError("يجب إدخال قراءة العداد الخاصة بوحدة العتاد")
    value = _parse_decimal(value)
    if value < 0: raise ValueError("قيمة العداد لا يمكن أن تكون سالبة")
    date_value = reading_date or datetime.now(timezone.utc)
    if date_value.date() > datetime.now(timezone.utc).date(): raise ValueError("لا يمكن إدخال قراءة بتاريخ مستقبلي. اختر تاريخ اليوم أو تاريخًا سابقًا.")
    _ensure_not_duplicate_reading(db, equipment_id, date_value, value, unit_code)
    _validate_reading_position(db, equipment_id, date_value, value, unit_code)
    captured_status = normalize_equipment_status(equipment_status) if equipment_status is not None else normalize_equipment_status(equipment.operational_status)
    reading = MeterReading(equipment_id=equipment_id, reading_date=date_value, odometer=value if unit_code == "km" else None, hours=value if unit_code == "hours" else None, source="manual", equipment_status=captured_status, notes=(notes or "").strip()[:300] or None)
    db.add(reading); db.flush()
    _refresh_equipment_current(db, equipment, unit_code)
    db.commit(); db.refresh(reading); return reading
def create_bulk_readings(db: Session, rows: Iterable[dict], source: str = "import"):
    """Validate/import bulk rows. New imports use the equipment model; legacy callers may still send equipment_type."""
    clean_rows = list(rows)
    if not clean_rows: return 0, 0, [], [], []
    equipment_list = db.query(Equipment).options(joinedload(Equipment.equipment_type), joinedload(Equipment.equipment_model)).all()
    equipment_map: dict[str, Equipment] = {}
    for item in equipment_list:
        registration_key = normalize_registration(item.registration_number); asset_key = normalize_registration(item.asset_code)
        if registration_key: equipment_map[registration_key] = item
        if asset_key and asset_key not in equipment_map: equipment_map[asset_key] = item
    errors: list[str] = []; warnings: list[str] = []; candidates: list[dict] = []
    for index, row in enumerate(clean_rows, start=1):
        row_number = row.get("_row_number", index); registration_raw = row.get("registration"); registration = normalize_registration(registration_raw)
        if not registration: errors.append(f"الصف {row_number}: رقم التسجيل فارغ."); continue
        equipment = equipment_map.get(registration)
        if not equipment: errors.append(f"الصف {row_number}: رقم التسجيل {registration_raw} غير موجود في النظام."); continue
        model_raw = row.get("equipment_model"); legacy_type_raw = row.get("equipment_type")
        if model_raw is not None:
            supplied = " ".join(str(model_raw).strip().split()).casefold(); expected = str(equipment.equipment_model.name if equipment.equipment_model else "").strip()
            if not str(model_raw).strip(): errors.append(f"الصف {row_number}: الطراز فارغ للعتاد ذي رقم التسجيل {registration_raw}."); continue
            if expected and supplied != " ".join(expected.split()).casefold(): errors.append(f"الصف {row_number}: الطراز «{model_raw}» لا يطابق الطراز المسجل «{expected}» للعتاد ذي رقم التسجيل {registration_raw}."); continue
        else:
            if legacy_type_raw is None or not str(legacy_type_raw).strip(): errors.append(f"الصف {row_number}: نوع العتاد فارغ."); continue
            expected_type = str(equipment.equipment_type.name if equipment.equipment_type else "").strip(); supplied_type = " ".join(str(legacy_type_raw).strip().split()).casefold()
            if expected_type and supplied_type != " ".join(expected_type.split()).casefold(): errors.append(f"الصف {row_number}: نوع العتاد «{legacy_type_raw}» لا يطابق النوع المسجل «{expected_type}» لرقم التسجيل {registration_raw}."); continue
        reading_date = row.get("reading_date")
        if not isinstance(reading_date, datetime): errors.append(f"الصف {row_number}: تاريخ القراءة غير صحيح."); continue
        if reading_date.date() > datetime.now(timezone.utc).date(): errors.append(f"الصف {row_number}: تاريخ القراءة {reading_date:%d/%m/%Y} مستقبلي، ولم يتم حفظ القراءة."); continue
        unit_code = _unit(equipment); km_value = row.get("km_value"); hours_value = row.get("hours_value"); legacy_value = row.get("value"); has_km = km_value is not None and str(km_value).strip() != ""; has_hours = hours_value is not None and str(hours_value).strip() != ""
        if has_km and has_hours: expected = "الكيلومترات" if unit_code == "km" else "الساعات"; errors.append(f"الصف {row_number}: تم إدخال الكيلومترات والساعات معًا. العتاد يعمل بعداد {expected} فقط."); continue
        if has_km or has_hours:
            if unit_code == "km" and not has_km: errors.append(f"الصف {row_number}: العتاد {registration_raw} يعمل بالكيلومترات، لكن القيمة وُضعت في عمود الساعات."); continue
            if unit_code == "hours" and not has_hours: errors.append(f"الصف {row_number}: العتاد {registration_raw} يعمل بالساعات، لكن القيمة وُضعت في عمود الكيلومترات."); continue
            raw_value = km_value if unit_code == "km" else hours_value
        else: raw_value = legacy_value
        blank_value = raw_value is None or str(raw_value).strip() == ""
        if blank_value: value = Decimal("0"); warnings.append(f"الصف {row_number}: لم توجد قيمة للعداد للعتاد {registration_raw} بتاريخ {reading_date:%d/%m/%Y}؛ تم اعتبار القراءة صفرًا.")
        else:
            try: value = _parse_decimal(raw_value)
            except ValueError: errors.append(f"الصف {row_number}: قيمة العداد غير صحيحة، ولم يتم حفظ القراءة."); continue
        if value < 0: errors.append(f"الصف {row_number}: قيمة العداد سالبة ({value:g})، ولم يتم حفظ القراءة."); continue
        try: equipment_status = parse_equipment_status(row.get("equipment_status"))
        except ValueError as exc: errors.append(f"الصف {row_number}: {exc}"); continue
        candidates.append({"equipment": equipment, "reading_date": reading_date, "value": value, "blank_value": blank_value, "equipment_status": equipment_status, "_row_number": row_number})
    accepted: list[dict] = []; by_equipment: dict[int, list[dict]] = {}
    for item in candidates: by_equipment.setdefault(item["equipment"].id, []).append(item)
    for equipment_id, items in by_equipment.items():
        equipment = items[0]["equipment"]; unit_code = _unit(equipment); accepted_for_equipment: list[dict] = []
        for item in sorted(items, key=lambda x: (x["reading_date"], x["_row_number"])):
            value = item["value"]; invalid_reason = None
            comparisons = _meter_observations(db, equipment_id, unit_code) + [
                (x["reading_date"].date(), x["value"], "استيراد القراءات المركزية")
                for x in accepted_for_equipment
            ]
            for other_day, other_value, other_source in comparisons:
                day = item["reading_date"].date()
                if other_day == day:
                    if other_value == value:
                        invalid_reason = f"الصف {item['_row_number']}: القراءة ({value:g}) مكررة بتاريخ {day:%d/%m/%Y}، ومصدرها «{other_source}»."
                    elif not item["blank_value"]:
                        invalid_reason = f"الصف {item['_row_number']}: تعارض بتاريخ {day:%d/%m/%Y}؛ القراءة ({value:g}) تختلف عن ({other_value:g}) من مصدر «{other_source}»."
                    if invalid_reason: break
                elif not item["blank_value"] and other_day < day and other_value > value:
                    invalid_reason = f"الصف {item['_row_number']}: القراءة ({value:g}) أقل من القراءة المسجلة بتاريخ {other_day:%d/%m/%Y} ({other_value:g}) من مصدر «{other_source}»."; break
                elif not item["blank_value"] and other_day > day and other_value < value:
                    invalid_reason = f"الصف {item['_row_number']}: القراءة ({value:g}) أكبر من قراءة لاحقة بتاريخ {other_day:%d/%m/%Y} ({other_value:g}) من مصدر «{other_source}»."; break
            if invalid_reason: errors.append(invalid_reason)
            else: accepted_for_equipment.append(item); accepted.append(item)
    reading_ids: list[int] = []; affected: dict[int, Equipment] = {}
    for item in accepted:
        equipment = item["equipment"]; unit_code = _unit(equipment)
        reading = MeterReading(equipment_id=equipment.id, reading_date=item["reading_date"], odometer=item["value"] if unit_code == "km" else None, hours=item["value"] if unit_code == "hours" else None, source=source, equipment_status=item["equipment_status"], notes=None)
        db.add(reading); db.flush(); reading_ids.append(reading.id); affected[equipment.id] = equipment
    if accepted:
        for equipment in affected.values(): _refresh_equipment_current(db, equipment, _unit(equipment))
    db.commit(); return len(accepted), len(clean_rows) - len(accepted), errors, warnings, reading_ids
