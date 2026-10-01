from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session
from app.modules.equipment.models import Equipment
from app.modules.missions.models import Mission


def list_missions(db: Session):
    return db.query(Mission).order_by(Mission.start_date.desc(), Mission.id.desc()).all()


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
    if return_meter is not None and equipment.current_odometer is not None and return_meter > equipment.current_odometer:
        raise ValueError("عداد العودة أعلى من العداد الحالي للعتاد")


def add_mission(db: Session, data: dict):
    validate(db, data["equipment_id"], data["start_date"], data.get("end_date"), data.get("departure_meter"), data.get("return_meter"))
    mission = Mission(**data)
    db.add(mission)
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
    result = {"planned": 0, "running": 0, "completed": 0}
    for mission in list_missions(db):
        result[mission_status(mission)] += 1
    return result
