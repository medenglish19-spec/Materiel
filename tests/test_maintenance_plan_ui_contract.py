from pathlib import Path

from app.modules.maintenance.router import router


ROOT = Path(__file__).resolve().parents[1]
PLAN_TEMPLATE = ROOT / "app/modules/maintenance/templates/maintenance_plans.html"
ROUTER_SOURCE = ROOT / "app/modules/maintenance/router.py"


def _route_paths():
    return {(route.path, tuple(sorted(route.methods or ()))) for route in router.routes}


def test_maintenance_plan_routes_cover_page_management_and_execution():
    paths = _route_paths()
    assert ("/maintenance/plans", ("GET",)) in paths
    assert ("/api/maintenance/plans", ("GET",)) in paths
    assert ("/api/maintenance/plans", ("POST",)) in paths
    assert ("/api/maintenance/plans/{plan_id}", ("PUT",)) in paths
    assert ("/api/maintenance/plans/{plan_id}/operations", ("GET",)) in paths
    assert ("/api/maintenance/plans/{plan_id}/operations", ("POST",)) in paths
    assert ("/api/maintenance/plans/{plan_id}/operations/{operation_id}", ("DELETE",)) in paths
    assert ("/api/maintenance/plan-execution", ("POST",)) in paths


def test_maintenance_plan_ui_exposes_complete_controls():
    html = PLAN_TEMPLATE.read_text(encoding="utf-8")
    assert 'id="newPlan"' in html
    assert 'data-edit="' in html
    assert 'data-ops="' in html
    assert 'data-execute="' in html
    assert 'data-remove-op="' in html
    assert 'id="executionPanel"' in html
    assert 'id="executionForm"' in html
    assert 'id="executionEquipment"' in html
    assert 'id="executionDate"' in html
    assert 'id="executionMeter"' in html
    assert "api+'/plan-execution'" in html
    assert "لا يتم تعديل شروط العمليات من هنا." in html
    assert "سيتم إزالة العملية من الخطة فقط" in html


def test_plan_operation_add_rejects_inactive_operation():
    source = ROUTER_SOURCE.read_text(encoding="utf-8")
    assert 'if not operation.is_active: raise HTTPException(status_code=409, detail="لا يمكن إضافة عملية صيانة غير مفعلة إلى الخطة.")' in source
