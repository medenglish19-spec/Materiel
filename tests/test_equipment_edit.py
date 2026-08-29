from datetime import date

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.modules.equipment.models import Equipment
from app.modules.equipment.schemas import EquipmentCreate, EquipmentUpdate
from app.modules.equipment_types.models import EquipmentType, EquipmentModel
from app.modules.equipment import services


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Session = sessionmaker(bind=engine)


def test_equipment_edit_updates_fields_and_rejects_duplicate_identifiers():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = Session()
    try:
        type_a = EquipmentType(name="نوع اختبار التعديل", measurement_unit="km")
        type_b = EquipmentType(name="نوع آخر للتعديل", measurement_unit="hours")
        db.add_all([type_a, type_b])
        db.flush()
        model_a = EquipmentModel(name="طراز اختبار التعديل", equipment_type_id=type_a.id)
        model_b = EquipmentModel(name="طراز آخر للتعديل", equipment_type_id=type_b.id)
        db.add_all([model_a, model_b])
        db.flush()

        first = Equipment(
            asset_code="EDIT-1",
            registration_number="EDIT-REG-1",
            vin="EDIT-VIN-1",
            equipment_type_id=type_a.id,
            equipment_model_id=model_a.id,
        )
        second = Equipment(
            asset_code="EDIT-2",
            registration_number="EDIT-REG-2",
            vin="EDIT-VIN-2",
            equipment_type_id=type_a.id,
            equipment_model_id=model_a.id,
        )
        db.add_all([first, second])
        db.commit()
        db.refresh(first)

        services.update_equipment(
            db,
            first,
            EquipmentUpdate(
                registration_number="EDIT-REG-10",
                vin="EDIT-VIN-10",
                equipment_type_id=type_b.id,
                equipment_model_id=model_b.id,
                acquisition_date=date(2026, 8, 17),
                notes="تم تعديل بيانات العتاد",
            ),
        )
        assert first.registration_number == "EDIT-REG-10"
        assert first.vin == "EDIT-VIN-10"
        assert first.equipment_type_id == type_b.id
        assert first.equipment_model_id == model_b.id
        assert first.acquisition_date == date(2026, 8, 17)
        assert first.notes == "تم تعديل بيانات العتاد"


        try:
            services.create_equipment(
                db,
                EquipmentCreate(
                    equipment_type_id=type_a.id,
                    equipment_model_id=model_b.id,
                    registration_number="EDIT-BAD-MODEL",
                ),
            )
        except ValueError as exc:
            assert "لا ينتمي" in str(exc)
        else:
            raise AssertionError("equipment was created with a model from another type")

        try:
            services.update_equipment(db, first, EquipmentUpdate(registration_number="EDIT-REG-2"))
        except ValueError as exc:
            assert "رقم التسجيل" in str(exc)
        else:
            raise AssertionError("duplicate registration number was accepted")

        try:
            services.update_equipment(db, first, EquipmentUpdate(vin="EDIT-VIN-2"))
        except ValueError as exc:
            assert "رقم الهيكل" in str(exc)
        else:
            raise AssertionError("duplicate VIN was accepted")
    finally:
        db.close()
