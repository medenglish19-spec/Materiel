from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload
from app.modules.equipment.models import Equipment
from app.modules.missions.models import Driver, DriverSystemSetting, Mission
from app.modules.meter_readings.services import sync_current_meter, validate_meter_observation
from app.modules.meter_readings.models import MeterReading
from app.modules.meter_readings.source_values import source_reference


def get_driver_system_setting(db: Session) -> DriverSystemSetting:
    setting = db.query(DriverSystemSetting).filter(DriverSystemSetting.id == 1).first()
    if setting is None:
        setting = DriverSystemSetting(id=1, center_column_label="المركز")
        db.add(setting)
        db.commit()
        db.refresh(setting)
    return setting


def set_center_column_label(
    db: Session, label: str, user_id: int | None = None
) -> DriverSystemSetting:
    value = (label or "").strip()
    if not value:
        raise ValueError("تسمية العمود مطلوبة")
    if len(value) > 100:
        raise ValueError("تسمية العمود تتجاوز الحد الأقصى (100 حرف)")
    setting = get_driver_system_setting(db)
    setting.center_column_label = value
    setting.updated_by_id = user_id
    db.commit()
    db.refresh(setting)
    return setting


def list_drivers(db: Session):
    return (
        db.query(Driver)
        .options(joinedload(Driver.assigned_equipment).joinedload(Equipment.equipment_model))
        .order_by(Driver.last_name, Driver.first_name, Driver.id)
        .all()
    )


def list_active_assigned_drivers(db: Session):
    return (
        db.query(Driver)
        .options(
            joinedload(Driver.assigned_equipment).joinedload(Equipment.equipment_model)
        )
        .filter(
            Driver.is_active.is_(True),
            Driver.assigned_equipment_id.isnot(None),
        )
        .order_by(Driver.last_name, Driver.first_name, Driver.id)
        .all()
    )


def get_driver(db: Session, driver_id: int):
    return (
        db.query(Driver)
        .options(joinedload(Driver.assigned_equipment).joinedload(Equipment.equipment_model))
        .filter(Driver.id == driver_id)
        .first()
    )


def _driver_values(db: Session, data: dict, driver_id: int | None = None) -> dict:
    employee_number = (data.get("employee_number") or "").strip()
    if not employee_number and driver_id is not None:
        employee_number = (
            db.query(Driver.employee_number)
            .filter(Driver.id == driver_id)
            .scalar()
            or ""
        )
    if not employee_number:
        employee_number = f"DRV-{uuid4().hex}"
    values = {
        "employee_number": employee_number,
        "first_name": (data.get("first_name") or "").strip(),
        "last_name": (data.get("last_name") or "").strip(),
        "center": (data.get("center") or "").strip() or None,
        "license_class": (data.get("license_class") or "").strip(),
        "license_issue_date": data.get("license_issue_date"),
        "license_expiry_date": data.get("license_expiry_date"),
        "assigned_equipment_id": data.get("assigned_equipment_id") or None,
        "notes": (data.get("notes") or "").strip() or None,
    }
    required = {
        "employee_number": ("الرقم الوظيفي", 50),
        "first_name": ("الاسم", 100),
        "last_name": ("اللقب", 100),
        "license_class": ("صنف الرخصة", 50),
    }
    for field, (label, max_length) in required.items():
        if not values[field]:
            raise ValueError(f"{label} مطلوب")
        if len(values[field]) > max_length:
            raise ValueError(f"{label} يتجاوز الحد الأقصى ({max_length} حرفًا)")
    if values["center"] and len(values["center"]) > 120:
        raise ValueError("المركز يتجاوز الحد الأقصى (120 حرفًا)")
    if values["license_issue_date"] and values["license_issue_date"] > date.today():
        raise ValueError("تاريخ إصدار الرخصة لا يمكن أن يكون في المستقبل")
    if (
        values["license_issue_date"]
        and values["license_expiry_date"]
        and values["license_expiry_date"] < values["license_issue_date"]
    ):
        raise ValueError("تاريخ انتهاء الرخصة لا يمكن أن يسبق تاريخ إصدارها")

    duplicate = db.query(Driver.id).filter(
        Driver.employee_number == values["employee_number"]
    )
    if driver_id is not None:
        duplicate = duplicate.filter(Driver.id != driver_id)
    if duplicate.first():
        raise ValueError("الرقم الوظيفي مستخدم مسبقًا")

    equipment_id = values["assigned_equipment_id"]
    if equipment_id is not None:
        equipment = (
            db.query(Equipment)
            .options(joinedload(Equipment.equipment_model))
            .filter(Equipment.id == equipment_id)
            .first()
        )
        if not equipment:
            raise ValueError("العتاد المحدد غير موجود")
        if not equipment.equipment_model or not equipment.equipment_model.requires_driver:
            raise ValueError("يمكن تعيين السائق فقط إلى عتاد يتطلب سائقًا")
    return values


def list_driver_missions(db: Session, driver: Driver):
    linked_missions = (
        db.query(Mission)
        .options(
            joinedload(Mission.equipment).joinedload(Equipment.equipment_model),
            joinedload(Mission.driver),
        )
        .filter(Mission.driver_id == driver.id)
        .all()
    )
    full_name = f"{driver.first_name} {driver.last_name}".strip()
    another_driver_with_name = db.query(Driver.id).filter(
        Driver.id != driver.id,
        Driver.first_name == driver.first_name,
        Driver.last_name == driver.last_name,
    ).first()
    legacy_missions = []
    if full_name and not another_driver_with_name:
        legacy_missions = (
            db.query(Mission)
            .options(
                joinedload(Mission.equipment).joinedload(Equipment.equipment_model),
                joinedload(Mission.driver),
            )
            .filter(
                Mission.driver_id.is_(None),
                Mission.driver_name == full_name,
            )
            .all()
        )
    missions_by_id = {
        mission.id: mission for mission in linked_missions + legacy_missions
    }
    missions = sorted(
        missions_by_id.values(),
        key=lambda mission: (mission.start_date, mission.id),
        reverse=True,
    )
    reference_missions = {}
    for mission in missions:
        for attribute in ("departure_meter", "return_meter"):
            mission.__dict__[f"_pending_{attribute}"] = None
            reference = source_reference(mission, attribute)
            if reference:
                reference_missions[reference] = (mission, attribute)
    references = list(reference_missions)
    for start in range(0, len(references), 500):
        readings = db.query(
            MeterReading.source_reference,
            MeterReading.odometer,
            MeterReading.hours,
        ).filter(
            MeterReading.source_reference.in_(references[start : start + 500])
        ).all()
        for reference, odometer, hours in readings:
            mission, attribute = reference_missions[reference]
            mission.__dict__[f"_pending_{attribute}"] = (
                odometer if odometer is not None else hours
            )
    return missions, len(legacy_missions)


def create_driver(db: Session, data: dict) -> Driver:
    driver = Driver(**_driver_values(db, data))
    db.add(driver)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("الرقم الوظيفي مستخدم مسبقًا") from exc
    db.refresh(driver)
    return driver


def update_driver(db: Session, driver_id: int, data: dict) -> Driver:
    driver = db.query(Driver).filter(Driver.id == driver_id).first()
    if not driver:
        raise ValueError("السائق غير موجود")
    for field, value in _driver_values(db, data, driver_id).items():
        setattr(driver, field, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ValueError("الرقم الوظيفي مستخدم مسبقًا") from exc
    db.refresh(driver)
    return driver


def set_driver_active(db: Session, driver_id: int, is_active: bool) -> Driver:
    driver = db.query(Driver).filter(Driver.id == driver_id).first()
    if not driver:
        raise ValueError("السائق غير موجود")
    driver.is_active = is_active
    db.commit()
    db.refresh(driver)
    return driver


def license_expiry_alerts(drivers: list[Driver], today: date | None = None):
    today = today or date.today()
    window_end = today + timedelta(days=30)
    active_with_expiry = [
        driver
        for driver in drivers
        if driver.is_active and driver.license_expiry_date is not None
    ]
    expired = [
        driver for driver in active_with_expiry if driver.license_expiry_date < today
    ]
    expiring_soon = [
        driver
        for driver in active_with_expiry
        if today <= driver.license_expiry_date <= window_end
    ]
    return {
        "expired": expired,
        "expiring_soon": expiring_soon,
        "rows": sorted(
            expired + expiring_soon,
            key=lambda driver: (
                driver.license_expiry_date,
                driver.last_name,
                driver.first_name,
            ),
        ),
    }


def list_missions(db: Session):
    return (
        db.query(Mission)
        .options(
            joinedload(Mission.equipment).joinedload(Equipment.equipment_model),
            joinedload(Mission.driver),
        )
        .order_by(Mission.start_date.desc(), Mission.id.desc())
        .all()
    )


def mission_status(mission: Mission, today: date | None = None):
    today = today or date.today()
    if mission.end_date and mission.end_date < today:
        return "completed"
    if mission.start_date <= today:
        return "running"
    return "planned"


def validate(db: Session, equipment_id: int, start_date: date, end_date: date | None, departure_meter: Decimal | None, return_meter: Decimal | None):
    equipment = db.query(Equipment).filter(Equipment.id == equipment_id).first()
    if not equipment:
        raise ValueError("العتاد غير موجود")
    if equipment.operational_status != "available":
        raise ValueError(f"العتاد غير متاح حالياً (الوضعية: {equipment.operational_status})")
    if equipment.technical_condition == "broken":
        raise ValueError("العتاد عاطل ولا يمكن إسناده إلى مهمة")
    if end_date and end_date < start_date:
        raise ValueError("تاريخ نهاية المهمة لا يمكن أن يسبق بدايتها")
    if start_date > date.today():
        # التخطيط المسبق مسموح، لكن تاريخ نهاية مكتمل لا يمكن أن يكون مستقبليًا عند وجوده.
        if end_date and end_date <= date.today():
            raise ValueError("تواريخ المهمة غير متناسقة")
    if departure_meter is not None and departure_meter < 0:
        raise ValueError("عداد الانطلاق غير صالح")
    if return_meter is not None and departure_meter is not None and return_meter < departure_meter:
        raise ValueError("عداد العودة لا يمكن أن يقل عن عداد الانطلاق")
    if return_meter is not None and departure_meter is not None and end_date == start_date:
        raise ValueError("لا يمكن تسجيل قراءتي انطلاق وعودة للعداد في اليوم نفسه")
    unit = (equipment.equipment_type.measurement_unit if equipment.equipment_type else "km")
    if departure_meter is not None:
        validate_meter_observation(db, equipment_id, start_date, departure_meter, unit, "المهمة/الانطلاق")
    if return_meter is not None and end_date is not None:
        validate_meter_observation(db, equipment_id, end_date, return_meter, unit, "المهمة/العودة")


def add_mission(db: Session, data: dict):
    data = dict(data)
    driver_id = data.get("driver_id")
    if driver_id is not None:
        driver = db.query(Driver).filter(Driver.id == driver_id).first()
        if not driver or not driver.is_active:
            raise ValueError("السائق المحدد غير موجود أو غير نشط")
        if driver.assigned_equipment_id != data["equipment_id"]:
            raise ValueError("السائق غير معيّن إلى العتاد المحدد للمهمة")
        data["driver_name"] = f"{driver.first_name} {driver.last_name}".strip()
    validate(db, data["equipment_id"], data["start_date"], data.get("end_date"), data.get("departure_meter"), data.get("return_meter"))
    mission = Mission(**data)
    db.add(mission)
    db.flush()
    sync_current_meter(db, mission.equipment_id)
    # تحديث وضعية العتاد إلى "في مهمة"
    equipment = db.query(Equipment).filter(Equipment.id == data["equipment_id"]).first()
    if equipment:
        equipment.operational_status = "in_mission"
    db.commit(); db.refresh(mission)
    return mission


def sync_mission_statuses(db: Session):
    """تحديث وضعيات العتاد بناءً على المهمات الجارية والمنتهية"""
    today = date.today()
    # إعادة العتاد المتعلق بالمهمات المنتهية إلى "متاح"
    running_missions = db.query(Mission).filter(
        Mission.start_date <= today,
        (Mission.end_date.is_(None)) | (Mission.end_date >= today)
    ).all()
    running_equipment_ids = {m.equipment_id for m in running_missions}
    
    # إعادة العتاد الذي لا توجد له مهمة جارية إلى "متاح"
    mission_equipment_ids = {m.equipment_id for m in db.query(Mission).all()}
    equipment_with_missions = (
        db.query(Equipment).filter(Equipment.id.in_(mission_equipment_ids)).all()
        if mission_equipment_ids
        else []
    )
    
    for eq in equipment_with_missions:
        if eq.id not in running_equipment_ids and eq.operational_status == "in_mission":
            eq.operational_status = "available"
    
    db.commit()


def counts(db: Session):
    """احتساب حالة المهمات على مستوى العتاد، لا على مستوى سجلات المهمات."""
    result = {"planned": 0, "running": 0, "completed": 0}
    today = date.today()

    equipment = db.query(Equipment).all()
    missions_by_equipment = {}
    for mission in list_missions(db):
        missions_by_equipment.setdefault(mission.equipment_id, []).append(mission)

    for eq in equipment:
        missions = missions_by_equipment.get(eq.id, [])
        if not missions:
            continue

        statuses = {mission_status(mission, today) for mission in missions}
        if "running" in statuses:
            result["running"] += 1
        elif "planned" in statuses:
            result["planned"] += 1
        else:
            result["completed"] += 1

    return result
