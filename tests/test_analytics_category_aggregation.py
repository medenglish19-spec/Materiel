"""حماية ضد انحدار aggregation في تحليل السعة والجاهزية.

الخطأ كان: صفوف التصنيف لا تجمع عدّادات الحالات، فتفشل finalize
عند قراءة row["ready"] وتتكسّر صفحة التحليل بالكامل.
"""
import inspect
from pathlib import Path

from app.modules.equipment.analytics import (
    STATE_COUNTERS,
    build_capacity_readiness_analysis,
)


def _item(type_name, theoretical, condition, operational, model="M1"):
    from types import SimpleNamespace

    return SimpleNamespace(
        equipment_type=SimpleNamespace(
            name=type_name,
            theoretical_quantity=theoretical,
            category=SimpleNamespace(name="نقل"),
        ),
        equipment_model=SimpleNamespace(
            name=model, brand=SimpleNamespace(name="Test")
        ),
        technical_condition=condition,
        operational_status=operational,
    )


def test_every_category_row_carries_every_state_counter():
    """كل صف تصنيف يملك العدّادات التي تقرؤها finalize."""
    source = inspect.getsource(build_capacity_readiness_analysis)
    assert "STATE_COUNTERS" in source

    result = build_capacity_readiness_analysis([
        _item("حافلة", 2, "ready", "available"),
        _item("شاحنة", 1, "ready_restricted", "in_mission"),
        _item("جرافة", 0, "broken", "in_maintenance"),
    ])
    assert result["categories"]
    for category in result["categories"]:
        for key in STATE_COUNTERS:
            assert key in category, f"{category['name']} بلا {key}"
            assert isinstance(category[key], int)


def test_category_counters_sum_their_types():
    """عدّادات التصنيف تساوي مجموع أنواعه، لا تُترك عند الصفر."""
    result = build_capacity_readiness_analysis([
        _item("حافلة", 2, "ready", "available"),
        _item("حافلة", 2, "ready", "in_mission"),
        _item("شاحنة", 1, "broken", "in_maintenance"),
    ])
    category = result["categories"][0]
    for type_row in category["types"]:
        for key in STATE_COUNTERS:
            assert category[key] == sum(t[key] for t in category["types"]), key


def test_totals_match_the_sum_of_categories():
    """الإجمالي العام يطابق مجموع التصنيفات."""
    result = build_capacity_readiness_analysis([
        _item("حافلة", 3, "ready", "available"),
        _item("شاحنة", 0, "broken", "unavailable"),
    ])
    for key in STATE_COUNTERS:
        assert result["totals"][key] == sum(c[key] for c in result["categories"]), key


def test_readiness_percentages_are_computed_at_category_level():
    """نِسَب الجاهزية تُحسب على مستوى التصنيف بلا KeyError."""
    result = build_capacity_readiness_analysis([
        _item("حافلة", 4, "ready", "available"),
        _item("حافلة", 4, "broken", "in_maintenance"),
    ])
    category = result["categories"][0]
    assert category["actual"] == 2
    assert category["readiness_pct"] == 50.0
    assert category["broken_pct"] == 50.0
    assert category["available_pct"] == 50.0


def test_analysis_template_and_route_remain_reachable():
    """صفحة التحليل التي تعتمد هذا التجميع ما زالت مسجّلة."""
    from app.modules.equipment import router

    paths = {r.path for r in router.router.routes}
    assert "/equipment/analysis" in paths
    assert "/equipment/analysis/operational" in paths

    template = Path(
        "app/modules/equipment/templates/equipment_analysis.html"
    ).read_text(encoding="utf-8")
    assert "categories" in template
