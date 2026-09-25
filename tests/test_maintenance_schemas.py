from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.modules.maintenance.schemas import (
    MaintenanceOperationCreate,
    MaintenancePlanCreate,
    MaintenancePlanOperationCreate,
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


def test_plan_operation_rejects_nonpositive_override():
    with pytest.raises(ValidationError):
        MaintenancePlanOperationCreate(plan_id=1, operation_id=1, interval_days_override=0)

def test_execution_record_accepts_operation_without_legacy_rule():
    from datetime import date
    from app.modules.maintenance.schemas import MaintenanceRecordCreate

    item = MaintenanceRecordCreate(
        equipment_id=1,
        operation_id=7,
        maintenance_date=date(2026, 9, 25),
    )
    assert item.operation_id == 7
    assert item.rule_id is None


def test_execution_record_requires_operation_or_legacy_rule():
    from datetime import date
    from app.modules.maintenance.schemas import MaintenanceRecordCreate

    with pytest.raises(ValidationError):
        MaintenanceRecordCreate(
            equipment_id=1,
            maintenance_date=date(2026, 9, 25),
        )
