from datetime import date
from decimal import Decimal

from app.modules.maintenance.models import (
    MaintenancePlanExecution,
    MaintenancePlanExecutionOperation,
)
from app.modules.maintenance.schemas import MaintenancePlanExecutionOperationUpdate


def test_execution_percentage_is_per_cycle():
    execution = MaintenancePlanExecution(
        equipment_id=1,
        plan_id=2,
        execution_date=date(2026, 9, 25),
        meter_value=Decimal("10000"),
    )
    execution.operations.extend([
        MaintenancePlanExecutionOperation(operation_id=1, status="completed", sort_order=0),
        MaintenancePlanExecutionOperation(operation_id=2, status="completed", sort_order=1),
        MaintenancePlanExecutionOperation(operation_id=3, status="pending", sort_order=2),
        MaintenancePlanExecutionOperation(operation_id=4, status="pending", sort_order=3),
        MaintenancePlanExecutionOperation(operation_id=5, status="skipped", sort_order=4),
    ])

    assert execution.total_operations == 5
    assert execution.completed_operations == 2
    assert execution.execution_percentage == 40.0
    assert execution.is_complete is False


def test_new_execution_operations_start_pending():
    item = MaintenancePlanExecutionOperation(operation_id=11, sort_order=0)
    assert item.status == "pending"


def test_execution_operation_update_allows_only_known_states():
    assert MaintenancePlanExecutionOperationUpdate(status="completed").status == "completed"
    assert MaintenancePlanExecutionOperationUpdate(status="skipped").status == "skipped"
    assert MaintenancePlanExecutionOperationUpdate(status="pending").status == "pending"
