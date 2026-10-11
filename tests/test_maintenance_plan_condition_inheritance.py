"""وراثة شرط الخطة لعملياتها، واستقلال العمليات المستقلة.

يغطي هذا الملف سيناريوهات القاعدة الجديدة:

* إضافة عملية إلى خطة لا تشترط شرطًا مستقلًا للعملية على طراز الخطة؛
* تُقيَّم عملية الخطة بشرط خطتها لا بشرطها المستقل؛
* تغيير شرط الخطة يغيّر تقييم عملياتها؛
* العملية المستقلة تحتفظ بشرطها الخاص؛
* تغيير شرط الخطة لا يمس العملية المستقلة ولا التعريف العام؛
* العملية الواحدة في خطتين: كل سياق يحتفظ بشرطه؛
* قواعد الاعتماد والتنفيذ والبيانات والصلاحيات كما هي؛
* الصفحة الموحّدة تعرض الخطط وعملياتها والعمليات المستقلة دون شرط مضلل لعملية الخطة.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.dependencies import get_current_user
from app.database import model_registry  # noqa: F401  (يسجّل كل النماذج قبل أي استعلام)
from app.database import session as session_module
from app.database.base import Base
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentModel, EquipmentType
from app.modules.maintenance.models import (
    MaintenanceOperation,
    MaintenancePlan,
    MaintenancePlanOperation,
    maintenance_operation_models,
)
from app.modules.maintenance.router import router as maintenance_router
from app.modules.maintenance.services import (
    CONDITION_MODEL,
    condition_axis_text,
    operation_condition_for_model,
    operation_tasks_for_model,
    plan_condition,
    status_for,
)
from app.modules.users.models import User

PLAN_TEMPLATE = Path("app/modules/maintenance/templates/maintenance_plans.html")
ROUTER_SOURCE = Path("app/modules/maintenance/router.py")
SERVICES_SOURCE = Path("app/modules/maintenance/services.py")

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Session = sessionmaker(bind=engine, expire_on_commit=False)


def _link(db, operation, model_id, **condition):
    values = {"condition_source": CONDITION_MODEL, "equipment_model_id": model_id}
    values.update(condition)
    db.execute(
        maintenance_operation_models.insert().values(operation_id=operation.id, **values)
    )


def _operation(db, name, model_id, **condition):
    operation = MaintenanceOperation(name=name)
    db.add(operation)
    db.flush()
    _link(db, operation, model_id, **condition)
    db.commit()
    return operation


def _plan(db, name, model_id, approved=True, active=True, **intervals):
    plan = MaintenancePlan(
        name=name,
        equipment_model_id=model_id,
        is_active=active,
        is_approved=approved,
        **intervals,
    )
    db.add(plan)
    db.flush()
    db.commit()
    return plan


def _add_plan_operation(db, plan, operation, order=1):
    db.add(
        MaintenancePlanOperation(
            plan_id=plan.id, operation_id=operation.id, sort_order=order
        )
    )
    db.commit()


@pytest.fixture()
def ctx():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    db = Session()
    equipment_type = EquipmentType(name="نوع وراثة الشرط", measurement_unit="km")
    db.add(equipment_type)
    db.flush()
    model = EquipmentModel(name="طراز وراثة الشرط", equipment_type_id=equipment_type.id)
    db.add(model)
    db.flush()
    equipment = Equipment(
        asset_code="INH-1",
        registration_number="INH-1",
        equipment_type_id=equipment_type.id,
        equipment_model_id=model.id,
    )
    db.add(equipment)
    db.commit()
    ids = {"equipment_type": equipment_type.id, "model": model.id, "equipment": equipment.id}
    try:
        yield db, ids
    finally:
        db.close()


def _equipment_ns():
    return SimpleNamespace(equipment_type=SimpleNamespace(measurement_unit="km"))


def _plan_tasks(db, model_id):
    return {
        task.plan.id: task
        for task in operation_tasks_for_model(db, model_id)
        if task.plan is not None
    }


# ------------------------------------------- 2) عملية الخطة تُقيَّم بشرط خطتها


def test_plan_operation_is_evaluated_with_the_plan_condition(ctx):
    db, ids = ctx
    operation = _operation(db, "تغيير زيت", ids["model"], interval_km=Decimal("5000"))
    plan = _plan(db, "خطة عشرة آلاف", ids["model"], interval_km=Decimal("10000"))
    _add_plan_operation(db, plan, operation)

    tasks = operation_tasks_for_model(db, ids["model"])
    assert len(tasks) == 1
    task = tasks[0]
    assert task.plan is not None and task.plan.id == plan.id
    # الشرط الفعّال هو شرط الخطة لا شرط العملية المستقل.
    assert task.condition.interval_km == Decimal("10000.0")

    record = SimpleNamespace(maintenance_date=date(2026, 1, 1), meter_value=Decimal("0"))
    equipment = _equipment_ns()
    state, css, _remaining, _meta = status_for(
        task.operation, equipment, record, Decimal("9000"), condition=task.condition
    )
    # بشرط الخطة (10000) ما زال ضمن الموعد.
    assert state == "ضمن الموعد" and css == "success"
    # وبشرطه المستقل (5000) كان سيُعد مستحقًا الآن.
    own = operation_condition_for_model(db, operation.id, ids["model"])
    own_state, own_css, _r, _m = status_for(
        task.operation, equipment, record, Decimal("9000"), condition=own
    )
    assert own_state == "مستحقة الآن" and own_css == "danger"


# --------------------------------------- 3) تغيير شرط الخطة يغيّر تقييم عملياتها


def test_changing_the_plan_condition_changes_its_operations_evaluation(ctx):
    db, ids = ctx
    operation = _operation(db, "فحص فرامل", ids["model"], interval_km=Decimal("5000"))
    plan = _plan(db, "خطة قابلة للتغيير", ids["model"], interval_km=Decimal("10000"))
    _add_plan_operation(db, plan, operation)

    record = SimpleNamespace(maintenance_date=date(2026, 1, 1), meter_value=Decimal("0"))
    equipment = _equipment_ns()

    first = _plan_tasks(db, ids["model"])[plan.id]
    before, _c, _r, _m = status_for(
        operation, equipment, record, Decimal("9000"), condition=first.condition
    )
    assert before == "ضمن الموعد"

    plan.interval_km = Decimal("5000")
    db.commit()

    second = _plan_tasks(db, ids["model"])[plan.id]
    assert second.condition.interval_km == Decimal("5000.0")
    after, css, _r, _m = status_for(
        operation, equipment, record, Decimal("9000"), condition=second.condition
    )
    assert after == "مستحقة الآن" and css == "danger"


# ------------------------------------------- 4) العملية المستقلة تحتفظ بشرطها


def test_standalone_operation_keeps_its_own_condition(ctx):
    db, ids = ctx
    standalone = _operation(db, "عملية مستقلة", ids["model"], interval_km=Decimal("3000"))

    tasks = operation_tasks_for_model(db, ids["model"])
    assert len(tasks) == 1
    task = tasks[0]
    assert task.plan is None
    assert task.operation.id == standalone.id
    assert task.condition.interval_km == Decimal("3000.0")

    record = SimpleNamespace(maintenance_date=date(2026, 1, 1), meter_value=Decimal("0"))
    state, css, _r, _m = status_for(
        task.operation, _equipment_ns(), record, Decimal("4000"), condition=task.condition
    )
    assert state == "مستحقة الآن" and css == "danger"


# ------------------- 5) تغيير شرط الخطة لا يمسّ المستقلة ولا التعريف العام


def test_changing_a_plan_condition_does_not_touch_standalone_or_general_definition(ctx):
    db, ids = ctx
    in_plan = _operation(db, "عملية داخل خطة", ids["model"], interval_km=Decimal("5000"))
    standalone = _operation(db, "عملية بلا خطة", ids["model"], interval_km=Decimal("3000"))
    plan = _plan(db, "خطة أ", ids["model"], interval_km=Decimal("10000"))
    _add_plan_operation(db, plan, in_plan)

    plan.interval_km = Decimal("7000")
    db.commit()

    # الشرط المستقل للعملية المستقلة لم يتغير.
    assert operation_condition_for_model(db, standalone.id, ids["model"]).interval_km == Decimal("3000.0")
    # والشرط المستقل لعملية الخطة لم يتغير أيضًا (لم يُكتب عليه شرط الخطة).
    assert operation_condition_for_model(db, in_plan.id, ids["model"]).interval_km == Decimal("5000.0")
    # والتعريف العام للعملية لم يتغير.
    assert db.get(MaintenanceOperation, in_plan.id).name == "عملية داخل خطة"


# --------------- 6) العملية في خطتين: كل سياق يحتفظ بشرطه ولا يتأثر بالآخر


def test_operation_shared_between_two_plans_keeps_each_context_independent(ctx):
    db, ids = ctx
    operation = _operation(db, "عملية مشتركة", ids["model"], interval_km=Decimal("5000"))
    plan_a = _plan(db, "خطة أ", ids["model"], interval_km=Decimal("10000"))
    plan_b = _plan(db, "خطة ب", ids["model"], interval_km=Decimal("30000"))
    _add_plan_operation(db, plan_a, operation)
    _add_plan_operation(db, plan_b, operation)

    tasks = _plan_tasks(db, ids["model"])
    assert tasks[plan_a.id].condition.interval_km == Decimal("10000.0")
    assert tasks[plan_b.id].condition.interval_km == Decimal("30000.0")

    # تغيير شرط خطة أ لا يغيّر تقييم العملية ضمن خطة ب.
    plan_a.interval_km = Decimal("2000")
    db.commit()

    tasks = _plan_tasks(db, ids["model"])
    assert tasks[plan_a.id].condition.interval_km == Decimal("2000.0")
    assert tasks[plan_b.id].condition.interval_km == Decimal("30000.0")


def test_plan_condition_is_derived_at_read_time_and_never_persisted(ctx):
    db, ids = ctx
    operation = _operation(db, "عملية وقت القراءة", ids["model"], interval_km=Decimal("5000"))
    plan = _plan(db, "خطة وقت القراءة", ids["model"], interval_km=Decimal("12000"))
    _add_plan_operation(db, plan, operation)

    task = _plan_tasks(db, ids["model"])[plan.id]
    assert task.condition.interval_km == Decimal("12000.0")
    # لا يُكتب شرط الخطة على الصف المشترك للعملية مع طرازها.
    assert operation_condition_for_model(db, operation.id, ids["model"]).interval_km == Decimal("5000.0")

    # خطة بلا فاصل => شرط غير محدد لا فاصل مُختلق.
    empty_plan = _plan(db, "خطة بلا فاصل", ids["model"], interval_km=None)
    assert plan_condition(empty_plan).is_defined is False


# ----------------------------------- 7) اعتماد/تنفيذ/بيانات/صلاحيات كما هي

def _operation_payload(name, conditions=None, **extra):
    payload = {"name": name, "equipment_model_conditions": conditions or []}
    payload.update(extra)
    return payload


@pytest.fixture()
def api():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    seed = Session()
    equipment_type = EquipmentType(name="نوع واجهة الوراثة", measurement_unit="km")
    seed.add(equipment_type)
    seed.flush()
    model_a = EquipmentModel(name="طراز واجهة أ", equipment_type_id=equipment_type.id)
    model_b = EquipmentModel(name="طراز واجهة ب", equipment_type_id=equipment_type.id)
    seed.add_all([model_a, model_b])
    seed.flush()
    equipment_a = Equipment(
        asset_code="API-INH-A",
        registration_number="API-INH-A",
        equipment_type_id=equipment_type.id,
        equipment_model_id=model_a.id,
    )
    seed.add(equipment_a)
    seed.add(User(id=1, username="inh-admin", full_name="مسؤول", hashed_password="x", role="admin", is_active=True))
    seed.commit()
    ids = {
        "equipment_type": equipment_type.id,
        "model_a": model_a.id,
        "model_b": model_b.id,
        "equipment_a": equipment_a.id,
    }
    seed.close()

    app = FastAPI()
    app.include_router(maintenance_router)

    def override_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()

    def override_user():
        return User(id=1, username="inh-admin", full_name="مسؤول", hashed_password="x", role="admin", is_active=True)

    app.dependency_overrides[session_module.get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    with TestClient(app) as client:
        yield client, ids


def test_operation_is_added_to_a_plan_without_an_independent_model_condition(api):
    client, ids = api
    created = client.post(
        "/api/maintenance/operations",
        json=_operation_payload("عملية بلا شرط للطراز باء", [{"model_id": ids["model_a"], "interval_km": 10000}]),
    ).json()
    plan = client.post(
        "/api/maintenance/plans",
        json={"name": "خطة طراز باء", "equipment_model_id": ids["model_b"], "interval_km": 10000},
    ).json()

    added = client.post(
        f"/api/maintenance/plans/{plan['id']}/operations",
        json={"plan_id": plan["id"], "operation_id": created["id"], "sort_order": 1},
    )
    assert added.status_code == 201, added.text


def test_plan_approval_and_execution_rules_are_intact(api):
    client, ids = api
    created = client.post(
        "/api/maintenance/operations",
        json=_operation_payload("عملية تنفيذ", [{"model_id": ids["model_a"], "interval_km": 10000}]),
    ).json()
    plan = client.post(
        "/api/maintenance/plans",
        json={"name": "خطة تنفيذ", "equipment_model_id": ids["model_a"], "interval_km": 10000},
    ).json()
    assert client.post(
        f"/api/maintenance/plans/{plan['id']}/operations",
        json={"plan_id": plan["id"], "operation_id": created["id"], "sort_order": 1},
    ).status_code == 201

    payload = {
        "equipment_id": ids["equipment_a"],
        "plan_id": plan["id"],
        "operation_ids": [created["id"]],
        "maintenance_date": str(date(2026, 9, 25)),
        "meter_value": 100050,
    }
    # خطة غير معتمدة لا تُنفَّذ.
    blocked = client.post("/api/maintenance/plan-execution", json=payload)
    assert blocked.status_code == 409

    approved = client.post(f"/api/maintenance/plans/{plan['id']}/approve")
    assert approved.status_code == 200, approved.text

    executed = client.post("/api/maintenance/plan-execution", json=payload)
    assert executed.status_code in (200, 201), executed.text
    records = executed.json()
    assert len(records) == 1
    assert records[0]["plan_id"] == plan["id"]
    assert records[0]["operation_id"] == created["id"]


# --------------------------- 8) الصفحة الموحّدة + 9) لا شرط مضلل لعملية الخطة


def test_plans_page_exposes_the_unified_workspace_controls():
    html = PLAN_TEMPLATE.read_text(encoding="utf-8")
    # أزرار الإنشاء: خطة + عملية مستقلة.
    assert 'id="btnNewPlan"' in html and 'data-action="new-plan"' in html
    assert 'id="btnNewStandalone"' in html and 'data-action="new-standalone"' in html
    # اختيار الطراز والمؤشرات الملخصة.
    assert 'id="modelFilter"' in html
    assert 'id="summaryPlans"' in html and 'id="summaryStandalone"' in html
    # العرض الهرمي + إدارة عمليات الخطة + تعديل/إزالة.
    assert 'data-ops="' in html and 'data-remove-op="' in html
    assert 'data-edit="' in html and 'data-plan-id="' in html
    # محرر العملية المستقلة.
    assert 'id="standalonePanel"' in html and 'data-edit-standalone="' in html
    # نقاط النهاية الحقيقية.
    assert "api+'/plans'" in html
    assert "api+'/plans/'+id+'/operations'" in html


def test_plans_page_does_not_show_a_conflicting_member_operation_condition():
    html = PLAN_TEMPLATE.read_text(encoding="utf-8")
    # صفوف عمليات الخطة تُصرّح بأنها تتبع شرط الخطة، لا شرطًا مستقلًا.
    assert "يتبع شرط الخطة" in html
    assert "عمليات مستقلة" in html
    # نفس المعنى مُوثّق في الخدمة: شرط الخطة هو المرجع لعملياته.
    services = SERVICES_SOURCE.read_text(encoding="utf-8")
    assert "plan_condition" in services
    assert "operation_tasks_for_model" in services
    # الشرط الظاهر لعملية الخطة يأتي من الخطة نفسها.
    plan = SimpleNamespace(
        interval_km=Decimal("10000"), interval_hours=None, interval_days=None
    )
    assert condition_axis_text(plan_condition(plan)) == "10000 كم"


def test_router_exposes_plan_and_standalone_workspace_endpoints():
    source = ROUTER_SOURCE.read_text(encoding="utf-8")
    assert '@router.get("/maintenance/plans"' in source
    assert '@router.post("/api/maintenance/plans/{plan_id}/operations"' in source
    assert '@router.delete("/api/maintenance/plans/{plan_id}/operations/{operation_id}"' in source
    assert '@router.post("/api/maintenance/plans/{plan_id}/approve"' in source
    assert '@router.put("/api/maintenance/operations/{operation_id}"' in source
    # بوابة التوافق القديمة أُزيلت من مسار الإضافة.
    assert "check_plan_operation_condition_compatibility(plan" not in source
