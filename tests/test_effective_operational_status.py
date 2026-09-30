"""عقد الوضعية التشغيلية الفعّالة في قائمة العتاد.

منطق الوضعية الفعّالة (`effective_operational_status`: المعطوب غير متاح،
والمهمة الجارية تفرض «في مهمة») أُضيف في فرع الصيانة، ثم دُمج مع redesign
قائمة العتاد (بطاقات بلا جدول). هذه العقود تمنع فقدان أي من الطرفين في
أي دمج لاحق.
"""

import inspect
from pathlib import Path

TEMPLATE = Path("app/modules/equipment/templates/equipment_list.html")


def test_effective_status_service_is_importable():
    from app.modules.equipment import services

    assert callable(services.effective_operational_status)


def test_equipment_page_computes_and_passes_effective_statuses():
    from app.modules.equipment import router

    source = inspect.getsource(router.equipment_page)

    assert "services.effective_operational_status(db, item)" in source
    assert '"operational_statuses": operational_statuses' in source


def test_equipment_list_template_renders_the_effective_status():
    template = TEMPLATE.read_text(encoding="utf-8")

    assert "{% set current_status = operational_statuses[item.id] %}" in template
    # لا يجوز عرض الحقل المخزّن: هو ما يجعل القائمة تخالف المهمات الجارية.
    assert "item.operational_status" not in template
    assert 'data-status="{{ current_status }}"' in template