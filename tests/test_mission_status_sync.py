"""عقد انحدار لمزامنة وضعيات العتاد مع المهمات (M4).

يغطي الحالة التي كان استدعاء فيها معيار WHERE فارغًا `[]` فينهار
SQLAlchemy 2.1: قاعدة بيانات بلا أي مهمة.
"""

from datetime import date, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import model_registry  # noqa: F401  (يسجّل كل النماذج قبل create_all)
from app.database.base import Base
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentModel, EquipmentType
from app.modules.missions import services
from app.modules.missions.models import Mission

engine = create_engine(
    "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
Session = sessionmaker(bind=engine)


def _fixture():
    """عتاد واحد جاهز + مصنع مهمات."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = Session()
    equipment_type = EquipmentType(name="نوع اختبار المهمات", measurement_unit="km")
    db.add(equipment_type)
    db.flush()
    model = EquipmentModel(name="طراز اختبار المهمات", equipment_type_id=equipment_type.id)
    db.add(model)
    db.flush()
    equipment = Equipment(
        asset_code="MISSION-1",
        registration_number="900",
        equipment_type_id=equipment_type.id,
        equipment_model_id=model.id,
        operational_status="available",
    )
    db.add(equipment)
    db.commit()
    db.refresh(equipment)

    def mission(**overrides):
        values = {
            "equipment_id": equipment.id,
            "start_date": date.today() - timedelta(days=10),
            "end_date": None,
        }
        values.update(overrides)
        row = Mission(**values)
        db.add(row)
        db.commit()
        return row

    return db, equipment, mission


def test_sync_without_any_mission_does_not_crash():
    """بلا مهمات: لا معيار WHERE فارغ، ولا تغيير في وضعية العتاد."""
    db, equipment, _ = _fixture()
    try:
        equipment.operational_status = "in_mission"
        db.commit()

        services.sync_mission_statuses(db)

        db.refresh(equipment)
        assert equipment.operational_status == "in_mission", "لا مهمة = لا قرار"
    finally:
        db.close()


def test_finished_mission_returns_equipment_to_available():
    db, equipment, mission = _fixture()
    try:
        equipment.operational_status = "in_mission"
        db.commit()
        mission(end_date=date.today() - timedelta(days=1))

        services.sync_mission_statuses(db)

        db.refresh(equipment)
        assert equipment.operational_status == "available"
    finally:
        db.close()


def test_running_mission_keeps_equipment_in_mission():
    db, equipment, mission = _fixture()
    try:
        equipment.operational_status = "in_mission"
        db.commit()
        mission(start_date=date.today() - timedelta(days=1), end_date=None)

        services.sync_mission_statuses(db)

        db.refresh(equipment)
        assert equipment.operational_status == "in_mission"
    finally:
        db.close()