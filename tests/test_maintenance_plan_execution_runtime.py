from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentModel, EquipmentType
from app.modules.maintenance.models import MaintenanceOperation, MaintenancePlan, MaintenancePlanOperation, MaintenanceRecord
from app.modules.maintenance.router import api_plan_execution_create
from app.modules.maintenance.schemas import MaintenancePlanExecutionCreate


engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Session = sessionmaker(bind=engine)


def test_plan_execution_creates_one_record_per_active_operation():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = Session()
    try:
        equipment_type = EquipmentType(name="نوع اختبار تنفيذ الخطة", measurement_unit="km")
        db.add(equipment_type)
        db.flush()

        model = EquipmentModel(name="طراز اختبار تنفيذ الخطة", equipment_type_id=equipment_type.id)
        db.add(model)
        db.flush()

        equipment = Equipment(
            asset_code="PLAN-EXEC-1",
            registration_number="PLAN-EXEC-1",
            equipment_type_id=equipment_type.id,
            equipment_model_id=model.id,
        )
        db.add(equipment)
        db.flush()

        oil = MaintenanceOperation(
            name="تغيير زيت المحرك",
            interval_km=Decimal("10000"),
            warning_km=Decimal("500"),
            is_active=True,
        )
        brakes = MaintenanceOperation(
            name="فحص الفرامل",
            interval_days=180,
            warning_days=7,
            is_active=True,
        )
        disabled = MaintenanceOperation(
            name="عملية غير مفعلة",
            interval_km=Decimal("5000"),
            is_active=False,
        )
        plan = MaintenancePlan(
            equipment_model_id=model.id,
            name="الصيانة السداسية",
            interval_days=180,
            is_active=True,
        )
        db.add_all([oil, brakes, disabled, plan])
        db.flush()

        db.add_all([
            MaintenancePlanOperation(plan_id=plan.id, operation_id=oil.id, sort_order=1),
            MaintenancePlanOperation(plan_id=plan.id, operation_id=brakes.id, sort_order=2),
            MaintenancePlanOperation(plan_id=plan.id, operation_id=disabled.id, sort_order=3),
        ])
        db.commit()

        payload = MaintenancePlanExecutionCreate(
            equipment_id=equipment.id,
            plan_id=plan.id,
            maintenance_date=date(2026, 9, 25),
            meter_value=Decimal("50000"),
            work_order="WO-PLAN-1",
            workshop="الورشة الرئيسية",
        )

        records = api_plan_execution_create(
            payload=payload,
            db=db,
            current_user=SimpleNamespace(id=None),
        )

        assert len(records) == 2
        assert {record.operation_id for record in records} == {oil.id, brakes.id}
        assert {record.plan_id for record in records} == {plan.id}
        assert all(record.equipment_id == equipment.id for record in records)

        saved = db.query(MaintenanceRecord).filter(
            MaintenanceRecord.equipment_id == equipment.id,
            MaintenanceRecord.plan_id == plan.id,
        ).all()
        assert len(saved) == 2
        assert {record.operation_id for record in saved} == {oil.id, brakes.id}

        assert oil.interval_km == Decimal("10000")
        assert brakes.interval_days == 180
        assert disabled.is_active is False
    finally:
        db.close()


def test_plan_execution_rejects_plan_for_another_model_without_records():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = Session()
    try:
        equipment_type = EquipmentType(name="نوع اختبار حدود الخطة", measurement_unit="km")
        db.add(equipment_type)
        db.flush()

        model_a = EquipmentModel(name="طراز A", equipment_type_id=equipment_type.id)
        model_b = EquipmentModel(name="طراز B", equipment_type_id=equipment_type.id)
        db.add_all([model_a, model_b])
        db.flush()

        equipment = Equipment(
            asset_code="PLAN-BOUNDARY-1",
            equipment_type_id=equipment_type.id,
            equipment_model_id=model_a.id,
        )
        operation = MaintenanceOperation(
            name="عملية حدود الطراز",
            interval_km=Decimal("10000"),
            is_active=True,
        )
        plan = MaintenancePlan(
            equipment_model_id=model_b.id,
            name="خطة طراز B",
            interval_km=Decimal("10000"),
            is_active=True,
        )
        db.add_all([equipment, operation, plan])
        db.flush()
        db.add(MaintenancePlanOperation(plan_id=plan.id, operation_id=operation.id))
        db.commit()

        payload = MaintenancePlanExecutionCreate(
            equipment_id=equipment.id,
            plan_id=plan.id,
            maintenance_date=date(2026, 9, 25),
            meter_value=Decimal("50000"),
        )

        with pytest.raises(HTTPException) as exc:
            api_plan_execution_create(
                payload=payload,
                db=db,
                current_user=SimpleNamespace(id=None),
            )

        assert exc.value.status_code == 409
        assert "لا تخص طراز العتاد" in exc.value.detail
        assert db.query(MaintenanceRecord).count() == 0
    finally:
        db.close()
