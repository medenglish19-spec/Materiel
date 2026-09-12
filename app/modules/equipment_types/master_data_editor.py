from datetime import datetime, timezone
import json

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _clean(value):
    return str(value).strip() if value is not None else ""


def _number(value, field, integer=False, minimum=0):
    if value in (None, ""):
        return None
    try:
        result = int(value) if integer else float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"القيمة في {field} غير صحيحة.") from exc
    if result < minimum:
        raise ValueError(f"القيمة في {field} لا يمكن أن تكون أقل من {minimum}.")
    return result


def _get_model(db: Session, model_id: int):
    row = db.execute(text("""
        SELECT em.id, em.name, em.equipment_type_id, em.brand_id,
               et.name AS type_name, eb.name AS brand_name
        FROM equipment_models em
        JOIN equipment_types et ON et.id = em.equipment_type_id
        LEFT JOIN equipment_brands eb ON eb.id = em.brand_id
        WHERE em.id = :id
    """), {"id": model_id}).mappings().first()
    if row is None:
        raise ValueError("الطراز المحدد غير موجود.")
    return row


def _configuration(db: Session, model_id: int, config_type: str, name: str):
    column = "tire_configuration_id" if config_type == "tire" else "battery_configuration_id"
    row = db.execute(text(f"""
        SELECT c.id, c.code, c.name, c.is_active
        FROM master_data_configurations c
        JOIN equipment_models m ON m.{column} = c.id
        WHERE m.id = :model_id AND c.config_type = :config_type
        LIMIT 1
    """), {"model_id": model_id, "config_type": config_type}).mappings().first()
    if row:
        return row

    prefix = "TIRE_MODEL" if config_type == "tire" else "BATTERY_MODEL"
    code = f"{prefix}_{model_id}"
    now = _now()
    try:
        db.execute(text("""
            INSERT INTO master_data_configurations
                (code, config_type, name, is_active, created_at, updated_at)
            VALUES (:code, :config_type, :name, 1, :created_at, :updated_at)
        """), {"code": code, "config_type": config_type, "name": name,
               "created_at": now, "updated_at": now})
    except IntegrityError as exc:
        raise ValueError("تعذر إنشاء إعداد Master Data للطراز. تحقق من عدم وجود تعارض في رمز الإعداد.") from exc
    config_id = db.execute(text("SELECT id FROM master_data_configurations WHERE code = :code"), {"code": code}).scalar_one()
    db.execute(text(f"UPDATE equipment_models SET {column} = :config_id WHERE id = :model_id"),
               {"config_id": config_id, "model_id": model_id})
    return {"id": config_id, "code": code, "name": name, "is_active": 1}


def get_editor_data(db: Session, model_id: int):
    model = _get_model(db, model_id)
    properties = db.execute(text("""
        SELECT id, property_key, property_label, value_text, value_number, unit, sort_order
        FROM master_data_model_properties
        WHERE equipment_model_id = :model_id
        ORDER BY sort_order, id
    """), {"model_id": model_id}).mappings().all()

    tire_config = _configuration_read(db, model_id, "tire")
    battery_config = _configuration_read(db, model_id, "battery")
    rules = db.execute(text("""
        SELECT id, name, interval_km, interval_hours, interval_days,
               warning_km, warning_days, is_active, description
        FROM maintenance_rules
        WHERE equipment_model_id = :model_id
        ORDER BY id
    """), {"model_id": model_id}).mappings().all()

    return {
        "model": dict(model),
        "properties": [dict(x) for x in properties],
        "tires": tire_config,
        "batteries": battery_config,
        "maintenance": [dict(x) for x in rules],
    }


def _configuration_read(db: Session, model_id: int, config_type: str):
    column = "tire_configuration_id" if config_type == "tire" else "battery_configuration_id"
    config = db.execute(text(f"""
        SELECT c.id, c.code, c.name, c.is_active
        FROM master_data_configurations c
        JOIN equipment_models m ON m.{column} = c.id
        WHERE m.id = :model_id AND c.config_type = :config_type
        LIMIT 1
    """), {"model_id": model_id, "config_type": config_type}).mappings().first()
    if not config:
        return {"id": None, "code": None, "name": None, "items": []}
    items = db.execute(text("""
        SELECT id, item_code, item_name, axle_number, side, position_type,
               sort_order, value_text, value_number, unit
        FROM master_data_configuration_items
        WHERE configuration_id = :configuration_id
        ORDER BY sort_order, id
    """), {"configuration_id": config["id"]}).mappings().all()
    return {"id": config["id"], "code": config["code"], "name": config["name"],
            "items": [dict(x) for x in items]}


def _save_properties(db: Session, model_id: int, rows):
    seen = set()
    for index, row in enumerate(rows or []):
        key = _clean(row.get("property_key"))
        label = _clean(row.get("property_label"))
        if not key and not label:
            continue
        if not key or not label:
            raise ValueError(f"خاصية رقم {index + 1}: يجب تحديد المفتاح والاسم.")
        if key in seen:
            raise ValueError(f"الخاصية {key} مكررة.")
        seen.add(key)
        number = _number(row.get("value_number"), "قيمة الخاصية")
        text_value = _clean(row.get("value_text")) or None
        if number is not None and text_value:
            raise ValueError(f"الخاصية {label}: استخدم قيمة نصية أو رقمية، وليس الاثنين معًا.")
        db.execute(text("""
            INSERT INTO master_data_model_properties
                (equipment_model_id, property_key, property_label, value_text, value_number, unit, sort_order, extra_json, created_at, updated_at)
            VALUES (:model_id, :key, :label, :text_value, :number, :unit, :sort_order, NULL, :created_at, :updated_at)
            ON CONFLICT(equipment_model_id, property_key) DO UPDATE SET
                property_label=excluded.property_label,
                value_text=excluded.value_text,
                value_number=excluded.value_number,
                unit=excluded.unit,
                sort_order=excluded.sort_order,
                updated_at=excluded.updated_at
        """), {"model_id": model_id, "key": key, "label": label, "text_value": text_value,
               "number": number, "unit": _clean(row.get("unit")) or None, "sort_order": index,
               "created_at": _now(), "updated_at": _now()})
    if seen:
        placeholders = ",".join(f":k{i}" for i in range(len(seen)))
        params = {f"k{i}": key for i, key in enumerate(seen)}
        params["model_id"] = model_id
        db.execute(text(f"DELETE FROM master_data_model_properties WHERE equipment_model_id=:model_id AND property_key NOT IN ({placeholders})"), params)
    else:
        db.execute(text("DELETE FROM master_data_model_properties WHERE equipment_model_id=:model_id"), {"model_id": model_id})


def _save_tire_items(db: Session, model_id: int, rows):
    config = _configuration(db, model_id, "tire", f"إطارات — {_get_model(db, model_id)['name']}")
    existing = {r["item_code"]: r for r in db.execute(text("""
        SELECT id, item_code, item_name, axle_number, side, position_type, sort_order, value_text, value_number, unit
        FROM master_data_configuration_items WHERE configuration_id=:id
    """), {"id": config["id"]}).mappings().all()}
    seen = set()
    for index, row in enumerate(rows or []):
        code = _clean(row.get("item_code")) or f"P{index + 1:02d}"
        name = _clean(row.get("item_name"))
        if not name:
            raise ValueError(f"موضع إطار رقم {index + 1}: يجب تحديد اسم الموضع.")
        if code in seen:
            raise ValueError(f"رمز موضع الإطار {code} مكرر.")
        seen.add(code)
        axle = _number(row.get("axle_number"), "المحور", integer=True)
        sort_order = index
        old = existing.get(code)
        if old:
            changed_identity = any(old[field] != value for field, value in {
                "item_name": name, "axle_number": axle, "side": _clean(row.get("side")) or None,
                "position_type": _clean(row.get("position_type")) or None,
            }.items())
            if changed_identity:
                materialized_code = f"MD-{model_id}-{code}"[:40]
                movements = db.execute(text("""
                    SELECT COUNT(*) FROM tire_movements tm
                    JOIN tire_positions tp ON tp.id=tm.position_id
                    WHERE tp.code=:code
                """), {"code": materialized_code}).scalar_one()
                if movements:
                    raise ValueError(f"لا يمكن تغيير تعريف موضع الإطار {code} لأن له حركات تاريخية. أنشئ موضعًا جديدًا بدل إعادة تعريفه.")
            db.execute(text("""
                UPDATE master_data_configuration_items
                SET item_name=:name, axle_number=:axle, side=:side, position_type=:position_type,
                    sort_order=:sort_order, value_text=:value_text, value_number=NULL, unit=:unit, updated_at=:updated_at
                WHERE id=:id
            """), {"id": old["id"], "name": name, "axle": axle, "side": _clean(row.get("side")) or None,
                   "position_type": _clean(row.get("position_type")) or None, "sort_order": sort_order,
                   "value_text": _clean(row.get("size")) or None, "unit": "size", "updated_at": _now()})
        else:
            db.execute(text("""
                INSERT INTO master_data_configuration_items
                (configuration_id,item_code,item_name,axle_number,side,position_type,sort_order,value_text,value_number,unit,extra_json,created_at,updated_at)
                VALUES (:configuration_id,:code,:name,:axle,:side,:position_type,:sort_order,:value_text,NULL,'size',NULL,:created_at,:updated_at)
            """), {"configuration_id": config["id"], "code": code, "name": name, "axle": axle,
                   "side": _clean(row.get("side")) or None, "position_type": _clean(row.get("position_type")) or None,
                   "sort_order": sort_order, "value_text": _clean(row.get("size")) or None,
                   "created_at": _now(), "updated_at": _now()})
    for code, old in existing.items():
        if code not in seen:
            materialized_code = f"MD-{model_id}-{code}"[:40]
            movements = db.execute(text("""
                SELECT COUNT(*) FROM tire_movements tm
                JOIN tire_positions tp ON tp.id=tm.position_id
                WHERE tp.code=:code
            """), {"code": materialized_code}).scalar_one()
            if movements:
                raise ValueError(f"لا يمكن حذف موضع الإطار {code} لأن له حركات تاريخية.")
            db.execute(text("DELETE FROM master_data_configuration_items WHERE id=:id"), {"id": old["id"]})


def _save_battery_items(db: Session, model_id: int, rows):
    config = _configuration(db, model_id, "battery", f"بطاريات — {_get_model(db, model_id)['name']}")
    existing = {r["item_code"]: r for r in db.execute(text("""
        SELECT id, item_code FROM master_data_configuration_items WHERE configuration_id=:id
    """), {"id": config["id"]}).mappings().all()}
    seen = set()
    for index, row in enumerate(rows or []):
        code = _clean(row.get("item_code")) or f"B{index + 1:02d}"
        name = _clean(row.get("item_name")) or f"بطارية {index + 1}"
        if code in seen:
            raise ValueError(f"رمز متطلب البطارية {code} مكرر.")
        seen.add(code)
        count = _number(row.get("count"), "عدد البطاريات", integer=True)
        voltage = _number(row.get("voltage"), "الجهد")
        capacity = _number(row.get("capacity"), "السعة")
        db.execute(text("""
            INSERT INTO master_data_configuration_items
                (configuration_id,item_code,item_name,sort_order,value_text,value_number,unit,extra_json,created_at,updated_at)
            VALUES (:configuration_id,:code,:name,:sort_order,:value_text,:value_number,:unit,:extra_json,:created_at,:updated_at)
            ON CONFLICT(configuration_id,item_code) DO UPDATE SET
                item_name=excluded.item_name, sort_order=excluded.sort_order,
                value_text=excluded.value_text, value_number=excluded.value_number,
                unit=excluded.unit, extra_json=excluded.extra_json, updated_at=excluded.updated_at
        """), {"configuration_id": config["id"], "code": code, "name": name, "sort_order": index,
               "value_text": _clean(row.get("specification")) or None,
               "value_number": capacity, "unit": "Ah", "extra_json": json.dumps({"count": count, "voltage": voltage}, ensure_ascii=False),
               "created_at": _now(), "updated_at": _now()})
    if seen:
        placeholders = ",".join(f":b{i}" for i in range(len(seen)))
        params = {f"b{i}": code for i, code in enumerate(seen)}
        params["configuration_id"] = config["id"]
        db.execute(text(f"DELETE FROM master_data_configuration_items WHERE configuration_id=:configuration_id AND item_code NOT IN ({placeholders})"), params)
    else:
        db.execute(text("DELETE FROM master_data_configuration_items WHERE configuration_id=:configuration_id"), {"configuration_id": config["id"]})


def _save_maintenance(db: Session, model, rows):
    seen = set()
    for index, row in enumerate(rows or []):
        rule_id = row.get("id")
        name = _clean(row.get("name"))
        if not name:
            continue
        key = (str(rule_id) if rule_id else "new", name)
        if key in seen:
            raise ValueError(f"قاعدة الصيانة {name} مكررة.")
        seen.add(key)
        km = _number(row.get("interval_km"), "فاصل الكيلومترات")
        hours = _number(row.get("interval_hours"), "فاصل الساعات")
        days = _number(row.get("interval_days"), "فاصل الأيام", integer=True)
        if km is None and hours is None and days is None:
            raise ValueError(f"قاعدة الصيانة {name}: يجب تحديد فاصل واحد على الأقل.")
        warning_km = _number(row.get("warning_km"), "تحذير الكيلومترات")
        warning_days = _number(row.get("warning_days"), "تحذير الأيام", integer=True)
        active = 1 if row.get("is_active", True) else 0
        if rule_id:
            exists = db.execute(text("SELECT id FROM maintenance_rules WHERE id=:id AND equipment_model_id=:model_id"), {"id": rule_id, "model_id": model["id"]}).scalar_one_or_none()
            if exists is None:
                raise ValueError(f"قاعدة الصيانة رقم {rule_id} غير مرتبطة بهذا الطراز.")
            db.execute(text("""
                UPDATE maintenance_rules SET name=:name, interval_km=:km, interval_hours=:hours,
                    interval_days=:days, warning_km=:warning_km, warning_days=:warning_days,
                    is_active=:active, description=:description
                WHERE id=:id
            """), {"id": rule_id, "name": name, "km": km, "hours": hours, "days": days,
                   "warning_km": warning_km, "warning_days": warning_days, "active": active,
                   "description": _clean(row.get("description")) or None})
            seen.add(str(rule_id))
        else:
            new_id = db.execute(text("""
                INSERT INTO maintenance_rules
                    (name,equipment_type_id,equipment_model_id,interval_km,interval_hours,interval_days,warning_km,warning_days,is_active,description)
                VALUES (:name,:type_id,:model_id,:km,:hours,:days,:warning_km,:warning_days,:active,:description)
                RETURNING id
            """), {"name": name, "type_id": model["equipment_type_id"], "model_id": model["id"], "km": km,
                   "hours": hours, "days": days, "warning_km": warning_km, "warning_days": warning_days,
                   "active": active, "description": _clean(row.get("description")) or None}).scalar_one()
            seen.add(str(new_id))
    existing = db.execute(text("SELECT id FROM maintenance_rules WHERE equipment_model_id=:model_id"), {"model_id": model["id"]}).scalars().all()
    submitted_ids = {int(x) for x in seen if x.isdigit()}
    for rule_id in existing:
        if rule_id not in submitted_ids:
            records = db.execute(text("SELECT COUNT(*) FROM maintenance_records WHERE rule_id=:id"), {"id": rule_id}).scalar_one()
            if records:
                raise ValueError(f"لا يمكن حذف قاعدة الصيانة رقم {rule_id} لأنها مرتبطة بسجلات صيانة منفذة.")
            db.execute(text("DELETE FROM maintenance_rules WHERE id=:id"), {"id": rule_id})


def save_editor_data(db: Session, model_id: int, payload: dict):
    model = _get_model(db, model_id)
    _save_properties(db, model_id, payload.get("properties", []))
    _save_tire_items(db, model_id, payload.get("tires", []))
    _save_battery_items(db, model_id, payload.get("batteries", []))
    _save_maintenance(db, model, payload.get("maintenance", []))
    db.commit()
    return get_editor_data(db, model_id)
