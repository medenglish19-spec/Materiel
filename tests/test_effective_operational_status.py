"""عقود وقواعد الوضعية التشغيلية الفعّالة في قائمة العتاد.

منطق الوضعية الفعّالة (`effective_operational_status`: المعطوب غير متاح، والمهمة
الجارية تفرض «في مهمة») أُضيف في فرع الصيانة، ثم دُمج مع redesign قائمة العتاد
(بطاقات بلا جدول).

الجزء الأول عقود توصيل (تمنع فقدان أي طرف في أي دمج لاحق)، والجزء الثاني قواعد
العمل نفسها — لم تكن مغطاة بأي اختبار وحدة قبل هذا الملف.
"""

import inspect
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import model_registry  # noqa: F401  (يسجّل كل النماذج قبل create_all)
from app.database.base import Base
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentModel, EquipmentType
from app.modules.missions.models import Mission

TEMPLATE = Path("app/modules/equipment/templates/equipment_list.html")

engine = create_engine(
    "sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
)
Session = sessionmaker(bind=engine)

MISSION_QUERIES = []


@event.listens_for(engine, "before_cursor_execute")
def _record_mission_queries(conn, cursor, statement, parameters, context, executemany):
    """مراقب عدّ استعلامات المهمات، لإثبات غياب N+1 في الدفعة."""
    if "missions" in statement:
        MISSION_QUERIES.append(statement)


def _fixture():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    return Session()


def _add_equipment(db, code, **overrides):
    equipment_type = db.query(EquipmentType).filter_by(name="نوع اختبار الوضعية").one_or_none()
    if equipment_type is None:
        equipment_type = EquipmentType(name="نوع اختبار الوضعية", measurement_unit="km")
        db.add(equipment_type)
        db.flush()
        db.add(EquipmentModel(name="طراز اختبار الوضعية", equipment_type_id=equipment_type.id))
        db.flush()
    values = {
        "asset_code": code,
        "equipment_type_id": equipment_type.id,
        "operational_status": "available",
        "technical_condition": "ready",
    }
    values.update(overrides)
    equipment = Equipment(**values)
    db.add(equipment)
    db.commit()
    db.refresh(equipment)
    return equipment


def _add_mission(db, equipment, **overrides):
    values = {
        "equipment_id": equipment.id,
        "start_date": date.today() - timedelta(days=3),
        "end_date": None,
    }
    values.update(overrides)
    mission = Mission(**values)
    db.add(mission)
    db.commit()
    return mission


# ----------------------------------------------------------------- عقود التوصيل


def test_effective_status_service_is_importable():
    from app.modules.equipment import services

    assert callable(services.effective_operational_status)
    assert callable(services.effective_operational_statuses)


def test_equipment_page_computes_and_passes_effective_statuses():
    from app.modules.equipment import router

    source = inspect.getsource(router.equipment_page)

    assert "services.effective_operational_statuses(db, items)" in source
    assert '"operational_statuses": operational_statuses' in source
    # ممنوع الاستدعاء المفرد داخل حلقة (كان مصدر N+1).
    assert "effective_operational_status(db, item)" not in source


def test_equipment_list_template_renders_the_effective_status():
    template = TEMPLATE.read_text(encoding="utf-8")

    assert "{% set current_status = operational_statuses[item.id] %}" in template
    # لا يجوز عرض الحقل المخزّن: هو ما يجعل القائمة تخالف المهمات الجارية.
    assert "item.operational_status" not in template
    assert 'data-status="{{ current_status }}"' in template


# ------------------------------------------------------------------ قواعد العمل


def test_broken_equipment_is_unavailable_even_with_an_active_mission():
    from app.modules.equipment import services

    db = _fixture()
    try:
        equipment = _add_equipment(db, "EFF-1", technical_condition="broken")
        _add_mission(db, equipment)

        assert services.effective_operational_status(db, equipment) == "unavailable"
    finally:
        db.close()


def test_maintenance_and_workshop_states_are_kept_even_with_an_active_mission():
    from app.modules.equipment import services

    for stored in ("in_maintenance", "in_external_workshop", "unavailable"):
        db = _fixture()
        try:
            equipment = _add_equipment(db, f"EFF-{stored}", operational_status=stored)
            _add_mission(db, equipment)

            assert services.effective_operational_status(db, equipment) == stored
        finally:
            db.close()


def test_active_mission_makes_available_equipment_in_mission():
    from app.modules.equipment import services

    db = _fixture()
    try:
        equipment = _add_equipment(db, "EFF-2")
        _add_mission(db, equipment, end_date=None)

        assert services.effective_operational_status(db, equipment) == "in_mission"
    finally:
        db.close()


def test_finished_mission_leaves_equipment_available():
    from app.modules.equipment import services

    db = _fixture()
    try:
        equipment = _add_equipment(db, "EFF-3")
        _add_mission(db, equipment, end_date=date.today() - timedelta(days=1))

        assert services.effective_operational_status(db, equipment) == "available"
    finally:
        db.close()


def test_mission_ending_today_is_not_counted_as_running():
    """الحد الفاصل: المهمة المنتهية اليوم انتهت فعلاً (المعيار end_date > today)."""
    from app.modules.equipment import services

    db = _fixture()
    try:
        equipment = _add_equipment(db, "EFF-4")
        _add_mission(db, equipment, end_date=date.today())

        assert services.effective_operational_status(db, equipment) == "available"
    finally:
        db.close()


def test_mission_that_has_not_started_is_not_counted_as_running():
    from app.modules.equipment import services

    db = _fixture()
    try:
        equipment = _add_equipment(db, "EFF-6")
        _add_mission(db, equipment, start_date=date.today() + timedelta(days=2))

        assert services.effective_operational_status(db, equipment) == "available"
    finally:
        db.close()


def test_equipment_without_any_mission_stays_available():
    from app.modules.equipment import services

    db = _fixture()
    try:
        equipment = _add_equipment(db, "EFF-5")

        assert services.effective_operational_status(db, equipment) == "available"
    finally:
        db.close()


# ------------------------------------------------------- الدفعة وغياب N+1


def test_batch_call_uses_one_mission_query_for_the_whole_page():
    """صفحة /equipment كانت تستدعي استعلام مهمة لكل قطعة؛ الدفعة استعلام واحد."""
    from app.modules.equipment import services

    db = _fixture()
    try:
        items = [_add_equipment(db, f"EFF-BATCH-{i}") for i in range(6)]
        _add_mission(db, items[0])
        _add_mission(db, items[3])

        MISSION_QUERIES.clear()
        statuses = services.effective_operational_statuses(db, items)

        assert len(MISSION_QUERIES) == 1, f"توقّع استعلام واحد، وجد {len(MISSION_QUERIES)}"
        assert statuses[items[0].id] == "in_mission"
        assert statuses[items[3].id] == "in_mission"
        assert statuses[items[1].id] == "available"
    finally:
        db.close()


def test_batch_call_matches_the_single_item_call():
    from app.modules.equipment import services

    db = _fixture()
    try:
        items = [_add_equipment(db, f"EFF-SAME-{i}") for i in range(3)]
        _add_mission(db, items[2])

        batch = services.effective_operational_statuses(db, items)
        singles = {item.id: services.effective_operational_status(db, item) for item in items}

        assert batch == singles
    finally:
        db.close()


def test_empty_batch_issues_no_query():
    from app.modules.equipment import services

    db = _fixture()
    try:
        MISSION_QUERIES.clear()
        assert services.effective_operational_statuses(db, []) == {}
        assert MISSION_QUERIES == []
    finally:
        db.close()
