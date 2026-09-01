from datetime import date
from decimal import Decimal
from sqlalchemy.orm import Session
from app.modules.equipment.models import Equipment
from app.modules.missions.models import Mission


def list_missions(db: Session):
    return db.query(Mission).order_by(Mission.start_date.desc(), Mission.id.desc()).all()


def mission_status(mission: Mission, today: date | None = None):
    today = today or date.today()
    if mission.end_date and mission.end_date <= today:
        return "completed"
    if mission.start_date <= today:
        return "running"
    return "planned"


def validate(db: Session, equipment_id: int, start_date: date, end_date: date | None, departure_meter: Decimal | None, return_meter: Decimal | None):
    if not db.query(Equipment).filter(Equipment.id == equipment_id).first():
        raise ValueError("العتاد غير موجود")
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
    equipment = db.query(Equipment).filter(Equipment.id == equipment_id).first()
    if return_meter is not None and equipment.current_odometer is not None and return_meter > equipment.current_odometer:
        raise ValueError("عداد العودة أعلى من العداد الحالي للعتاد")


def add_mission(db: Session, data: dict):
    validate(db, data["equipment_id"], data["start_date"], data.get("end_date"), data.get("departure_meter"), data.get("return_meter"))
    mission = Mission(**data)
    db.add(mission); db.commit(); db.refresh(mission)
    return mission


def counts(db: Session):
    result = {"planned": 0, "running": 0, "completed": 0}
    for mission in list_missions(db):
        result[mission_status(mission)] += 1
    return result
