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
from app.modules.faults_repairs.models import Fault
from app.modules.users.models import User
from app.modules.equipment_types.models import EquipmentModel, EquipmentType
from app.modules.maintenance.models import MaintenanceOperation, MaintenancePlan, MaintenancePlanOperation, MaintenanceRecord
from app.modules.maintenance.router import api_plan_execution_create
from app.modules.maintenance.services import latest_records
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
            is_approved=True,
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
            operation_ids=[oil.id, brakes.id],
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
        assert all(record.is_scheduled is False for record in records)

        scheduled = MaintenanceRecord(
            equipment_id=equipment.id,
            operation_id=oil.id,
            plan_id=plan.id,
            maintenance_date=date(2026, 9, 26),
            meter_value=Decimal("60000"),
            status="scheduled",
            is_scheduled=True,
        )
        db.add(scheduled)
        db.commit()
        assert latest_records(db)[(equipment.id, oil.id)].id == records[0].id

        saved = db.query(MaintenanceRecord).filter(
            MaintenanceRecord.equipment_id == equipment.id,
            MaintenanceRecord.plan_id == plan.id,
        ).all()
        assert len(saved) == 3
        assert {record.operation_id for record in saved} == {oil.id, brakes.id}
        actual_saved = [record for record in saved if record.is_scheduled is False]
        assert len(actual_saved) == 2
        assert {record.operation_id for record in actual_saved} == {oil.id, brakes.id}
        assert scheduled in saved

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
            is_approved=True,
        )
        plan = MaintenancePlan(
            equipment_model_id=model_b.id,
            name="خطة طراز B",
            interval_km=Decimal("10000"),
            is_active=True,
            is_approved=True,
        )
        db.add_all([equipment, operation, plan])
        db.flush()
        db.add(MaintenancePlanOperation(plan_id=plan.id, operation_id=operation.id))
        db.commit()

        payload = MaintenancePlanExecutionCreate(
            equipment_id=equipment.id,
            plan_id=plan.id,
            operation_ids=[operation.id],
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


def test_removing_plan_operation_preserves_library_and_history_and_blocks_future_selection():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = Session()
    try:
        equipment_type = EquipmentType(name="نوع اختبار مستقبلية الخطة", measurement_unit="km")
        db.add(equipment_type)
        db.flush()
        model = EquipmentModel(name="طراز اختبار مستقبلية الخطة", equipment_type_id=equipment_type.id)
        db.add(model)
        db.flush()
        equipment = Equipment(asset_code="PLAN-FUTURE-1", equipment_type_id=equipment_type.id, equipment_model_id=model.id)
        operation = MaintenanceOperation(name="عملية تبقى في المكتبة", interval_km=Decimal("10000"), is_active=True)
        plan = MaintenancePlan(equipment_model_id=model.id, name="خطة مستقبلية", interval_km=Decimal("10000"), is_active=True)
        db.add_all([equipment, operation, plan])
        db.flush()
        link = MaintenancePlanOperation(plan_id=plan.id, operation_id=operation.id)
        db.add(link)
        db.commit()

        first = api_plan_execution_create(
            payload=MaintenancePlanExecutionCreate(
                equipment_id=equipment.id,
                plan_id=plan.id,
                operation_ids=[operation.id],
                maintenance_date=date(2026, 9, 25),
                meter_value=Decimal("50000"),
            ),
            db=db,
            current_user=SimpleNamespace(id=None),
        )
        assert len(first) == 1
        record_id = first[0].id

        db.delete(link)
        db.commit()

        assert db.get(MaintenanceOperation, operation.id) is not None
        assert db.get(MaintenanceRecord, record_id) is not None
        assert db.query(MaintenancePlanOperation).filter(
            MaintenancePlanOperation.plan_id == plan.id,
            MaintenancePlanOperation.operation_id == operation.id,
        ).first() is None

        with pytest.raises(HTTPException) as exc:
            api_plan_execution_create(
                payload=MaintenancePlanExecutionCreate(
                    equipment_id=equipment.id,
                    plan_id=plan.id,
                    operation_ids=[operation.id],
                    maintenance_date=date(2026, 9, 26),
                    meter_value=Decimal("51000"),
                ),
                db=db,
                current_user=SimpleNamespace(id=None),
            )

        assert exc.value.status_code == 409
        assert "ليست ضمن العمليات" in exc.value.detail
        assert db.query(MaintenanceRecord).filter(MaintenanceRecord.id == record_id).count() == 1
    finally:
        db.close()
