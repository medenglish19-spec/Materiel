"""حماية: مسارات العتاد الأساسية موجودة وغير قابلة للحذف العرضي.

commit b58a336 (أعمال التحليلات) حذف 11 مسارًا من app/modules/equipment/router.py:
صفحة التفاصيل والتعديل والإنشاء والحذف والعدادات وواجهة /api، بينما بقيت
القوالب تشير إليها. هذه الاختبارات تمنع تكرار ذلك.
"""
import inspect

import pytest

from app.modules.equipment import router


def _routes():
    return {(m, r.path) for r in router.router.routes for m in getattr(r, "methods", set())}


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/equipment"),
        ("GET", "/equipment/analysis"),
        ("GET", "/equipment/analysis/operational"),
        ("GET", "/equipment/numerical-status"),
        ("GET", "/equipment/{equipment_id}"),
        ("GET", "/equipment/{equipment_id}/edit"),
        ("POST", "/equipment/create"),
        ("POST", "/equipment/{equipment_id}/edit"),
        ("POST", "/equipment/{equipment_id}/delete"),
        ("GET", "/equipment/{equipment_id}/meters"),
        ("POST", "/equipment/{equipment_id}/meters/create"),
        ("POST", "/equipment/{equipment_id}/meters/{reading_id}/update"),
        ("POST", "/equipment/{equipment_id}/meters/{reading_id}/delete"),
        ("GET", "/api/equipment"),
        ("GET", "/api/equipment/{equipment_id}"),
    ],
)
def test_core_equipment_route_is_registered(method, path):
    assert (method, path) in _routes(), f"المسار مفقود: {method} {path}"


def test_literal_routes_are_declared_before_the_equipment_id_placeholder():
    """FastAPI يطابق بالترتيب؛ الحرفية يجب أن تسبق /equipment/{equipment_id}."""
    paths = [r.path for r in router.router.routes]
    placeholder = paths.index("/equipment/{equipment_id}")
    for literal in ("/equipment/analysis", "/equipment/numerical-status"):
        assert paths.index(literal) < placeholder, literal


def test_detail_page_still_receives_installed_tire_and_battery_data():
    source = inspect.getsource(router.equipment_detail_page)
    assert "tire_services.installed_for_equipment" in source
    assert "installed_batteries" in source
    assert 'name="equipment_detail.html"' in source


def test_operational_analysis_route_uses_its_own_template():
    source = inspect.getsource(router.equipment_operational_analysis_page)
    assert 'name="equipment_operational_analysis.html"' in source
    assert "build_operational_analysis" in source


def test_equipment_detail_template_is_actually_reachable():
    """القالب غير مهجور: دالة الراوتر تشير إليه."""
    assert 'name="equipment_detail.html"' in inspect.getsource(router.equipment_detail_page)
