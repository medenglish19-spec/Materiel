from pathlib import Path


ROUTER = Path("app/modules/maintenance/router.py").read_text(encoding="utf-8")
SCHEMAS = Path("app/modules/maintenance/schemas.py").read_text(encoding="utf-8")
SERVICES = Path("app/modules/maintenance/services.py").read_text(encoding="utf-8")


def test_plan_execution_endpoint_is_operation_first_and_atomic():
    start = ROUTER.index('@router.post("/api/maintenance/plan-execution"')
    source = ROUTER[start:]

    assert "MaintenancePlanExecutionCreate" in source
    assert "MaintenancePlanOperation" in source
    assert "MaintenanceOperation.is_active.is_(True)" in source
    assert "for link in links:" in source
    assert "operation_id=operation.id" in source
    assert "plan_id=plan.id" in source
    assert "db.commit()" in source
    assert "db.rollback()" in source
    assert "لم يتم حفظ أي عملية من الخطة" in source


def test_plan_execution_schema_has_required_plan_and_equipment():
    start = SCHEMAS.index("class MaintenancePlanExecutionCreate")
    source = SCHEMAS[start:]

    assert "equipment_id: int" in source
    assert "plan_id: int" in source
    assert "maintenance_date: date" in source
    assert "meter_value: Decimal | None" in source


def test_plan_status_is_separate_from_operation_status():
    assert "def plan_status_for(" in SERVICES
    assert "operation-specific conditions remain authoritative" in SERVICES
    assert "def effective_plans_for_equipment(" in SERVICES
