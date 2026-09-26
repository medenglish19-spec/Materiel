from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.modules.maintenance.schemas import (
    MaintenanceOperationCreate,
    MaintenancePlanCreate,
    MaintenancePlanOperationCreate,
    MaintenancePlanExecutionCreate,
)


def test_operation_requires_at_least_one_interval():
    with pytest.raises(ValidationError):
        MaintenanceOperationCreate(name="تغيير الزيت")


def test_operation_accepts_single_interval():
    item = MaintenanceOperationCreate(name="تغيير الزيت", interval_km=Decimal("10000"))
    assert item.interval_km == Decimal("10000")


def test_operation_rejects_nonpositive_interval():
    with pytest.raises(ValidationError):
        MaintenanceOperationCreate(name="تغيير الزيت", interval_days=0)


def test_operation_rejects_negative_warning():
    with pytest.raises(ValidationError):
        MaintenanceOperationCreate(name="تغيير الزيت", interval_km=Decimal("10000"), warning_km=Decimal("-1"))


def test_plan_allows_optional_cadence_fields_for_compatibility():
    plan = MaintenancePlanCreate(name="خطة مخصصة", equipment_model_id=1)
    assert plan.interval_km is None
    assert plan.interval_hours is None
    assert plan.interval_days is None


def test_plan_operation_contains_membership_only():
    item = MaintenancePlanOperationCreate(plan_id=1, operation_id=1, sort_order=2)
    assert item.plan_id == 1
    assert item.operation_id == 1
    assert item.sort_order == 2


def test_execution_plan_requires_operation():
    from app.modules.maintenance.schemas import MaintenanceRecordCreate
    with pytest.raises(ValidationError):
        MaintenanceRecordCreate(equipment_id=1, plan_id=1, maintenance_date="2026-09-25")


def test_plan_execution_requires_plan_and_equipment():
    item = MaintenancePlanExecutionCreate(
        equipment_id=7,
        plan_id=3,
        maintenance_date="2026-09-25",
        meter_value=Decimal("10000"),
    )
    assert item.equipment_id == 7
    assert item.plan_id == 3
    assert item.meter_value == Decimal("10000")
