"""حذف خطط الصيانة: فردي وجماعي، مع الحفاظ على السجل التاريخي والمكتبة.

هذا الملف يحرس العقد الخادمي الجديد لمساحة عمل الخطط:

* ``DELETE /api/maintenance/plans/{plan_id}`` يحذف الخطة وروابط عملياتها فقط،
  ويرفض حذف الخطة عندما تكون مرتبطة بسجل تنفيذ تاريخي؛
* ``POST /api/maintenance/plans/bulk-delete`` يحذف الخطط المحددة ويردّ غير
  الموجودة داخل ``rejected`` مع سببها؛
* لا يُحذف أي تعريف عملية من مكتبة العمليات عند حذف خطة؛
* التحقق من المدخلات (قائمة غير فارغة، معرّفات موجبة) يبقى على الخادم.
"""

from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.dependencies import get_current_user
from app.database import session as session_module
from app.database.base import Base
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentModel, EquipmentType
from app.modules.maintenance.models import MaintenanceModelOperation, MaintenanceOperation, MaintenancePlan, MaintenanceOperationGroup  # noqa: F401
from app.modules.maintenance.router import router as maintenance_router
from app.modules.users.models import User

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Session = sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture()
def api():
    """واجهة REST الحقيقية على قاعدة مؤقتة معزولة (لا تُقرأ fleet_assets.db)."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    seed = Session()
    equipment_type = EquipmentType(name="نوع اختبار حذف الخطط", measurement_unit="km")
    seed.add(equipment_type)
    seed.flush()
    model_a = EquipmentModel(name="طراز حذف الخطط", equipment_type_id=equipment_type.id)
    model_b = EquipmentModel(name="طراز آخر للاختبار", equipment_type_id=equipment_type.id)
    seed.add_all([model_a, model_b])
    seed.flush()
    equipment_a = Equipment(
        asset_code="PLAN-DELETE-A",
        registration_number="PLAN-DELETE-A",
        equipment_type_id=equipment_type.id,
        equipment_model_id=model_a.id,
    )
    seed.add(equipment_a)
    seed.add(User(id=1, username="plan-delete-admin", full_name="مسؤول", hashed_password="x", role="admin", is_active=True))
    seed.commit()
    ids = {"model_a": model_a.id, "model_b": model_b.id, "equipment_a": equipment_a.id}
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
        return User(id=1, username="plan-delete-admin", full_name="مسؤول", hashed_password="x", role="admin", is_active=True)

    app.dependency_overrides[session_module.get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    with TestClient(app) as client:
        yield client, ids


def _create_operation(client, model_id, name="عملية حذف الخطة", interval_km=10000):
    response = client.post(
        "/api/maintenance/operations",
        json={
            "name": name,
            "equipment_model_conditions": [
                {"model_id": model_id, "condition_source": "model", "interval_km": interval_km}
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_plan(client, model_id, name="خطة حذف"):
    response = client.post(
        "/api/maintenance/plans",
        json={"name": name, "equipment_model_id": model_id, "interval_km": 10000},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _approve_plan_with_operation(client, model_id, plan_name="خطة محذوفة"):
    operation = _create_operation(client, model_id, name="عملية " + plan_name)
    plan = _create_plan(client, model_id, name=plan_name)
    linked = client.post(
        f"/api/maintenance/plans/{plan['id']}/operations",
        json={"plan_id": plan["id"], "operation_id": operation["id"], "sort_order": 1},
    )
    assert linked.status_code == 201, linked.text
    approved = client.post(f"/api/maintenance/plans/{plan['id']}/approve")
    assert approved.status_code == 200, approved.text
    return plan, operation


def _execute_plan(client, equipment_id, plan, operation):
    executed = client.post(
        "/api/maintenance/plan-execution",
        json={
            "equipment_id": equipment_id,
            "plan_id": plan["id"],
            "operation_ids": [operation["id"]],
            "maintenance_date": str(date(2026, 9, 25)),
            "meter_value": 1000,
        },
    )
    assert executed.status_code in (200, 201), executed.text
    return executed.json()


def test_delete_plan_with_execution_is_rejected_and_history_context_is_preserved(api):
    client, ids = api
    plan, operation = _approve_plan_with_operation(client, ids["model_a"])
    records = _execute_plan(client, ids["equipment_a"], plan, operation)
    record_id = records[0]["id"]

    deleted = client.delete(f"/api/maintenance/plans/{plan['id']}")
    assert deleted.status_code == 409, deleted.text
    assert "تاريخية" in deleted.json()["detail"]

    # تظل الخطة وعلاقتها بالسجل محفوظتين حتى لا يضيع سياق التنفيذ.
    plans = client.get("/api/maintenance/plans").json()
    assert any(item["id"] == plan["id"] for item in plans)

    execution = client.get("/api/maintenance/execution").json()
    survivor = next((row for row in execution if row["id"] == record_id), None)
    assert survivor is not None
    assert survivor["plan_id"] == plan["id"]
    assert survivor["equipment_id"] == ids["equipment_a"]

    # تعريف العملية لم يُحذف من المكتبة.
    operations = client.get("/api/maintenance/operations").json()
    assert any(item["id"] == operation["id"] for item in operations)


def test_delete_plan_with_only_scheduled_placeholder_is_allowed(api):
    client, ids = api
    plan, operation = _approve_plan_with_operation(
        client, ids["model_a"], plan_name="خطة بموعد غير منفذ"
    )
    scheduled = client.post(
        "/api/maintenance/execution",
        json={
            "equipment_id": ids["equipment_a"],
            "operation_id": operation["id"],
            "plan_id": plan["id"],
            "maintenance_date": "2026-10-12",
            "meter_value": 1000,
            "is_scheduled": True,
            "status": "scheduled",
        },
    )
    assert scheduled.status_code in (200, 201), scheduled.text
    record_id = scheduled.json()["id"]

    deleted = client.delete(f"/api/maintenance/plans/{plan['id']}")
    assert deleted.status_code == 204, deleted.text
    assert all(item["id"] != plan["id"] for item in client.get("/api/maintenance/plans").json())

    # The placeholder is not execution history and is preserved as a standalone schedule.
    record = next(
        row for row in client.get("/api/maintenance/execution").json()
        if row["id"] == record_id
    )
    assert record["is_scheduled"] is True
    assert record["status"] == "scheduled"
    assert record["plan_id"] is None
    assert record["operation_id"] == operation["id"]


def test_delete_missing_plan_returns_404(api):
    client, _ = api
    response = client.delete("/api/maintenance/plans/999999")
    assert response.status_code == 404
    assert response.json()["detail"] == "خطة الصيانة غير موجودة."


def test_bulk_delete_removes_existing_and_reports_missing(api):
    client, ids = api
    plan_one = _create_plan(client, ids["model_a"], name="خطة جماعية 1")
    plan_two = _create_plan(client, ids["model_a"], name="خطة جماعية 2")

    response = client.post(
        "/api/maintenance/plans/bulk-delete",
        json={"plan_ids": [plan_one["id"], plan_two["id"], 999999]},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["success"] == 2
    assert len(body["rejected"]) == 1
    rejected = body["rejected"][0]
    assert rejected["plan_id"] == 999999
    assert "غير موجودة" in rejected["reason"]

    plans = client.get("/api/maintenance/plans").json()
    assert plans == []


def test_bulk_delete_rejects_historical_plan_and_preserves_context(api):
    client, ids = api
    plan, operation = _approve_plan_with_operation(client, ids["model_a"], plan_name="خطة بسجل")
    records = _execute_plan(client, ids["equipment_a"], plan, operation)
    record_id = records[0]["id"]

    response = client.post(
        "/api/maintenance/plans/bulk-delete",
        json={"plan_ids": [plan["id"]]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["success"] == 0
    assert response.json()["rejected"][0]["plan_id"] == plan["id"]
    assert "تاريخية" in response.json()["rejected"][0]["reason"]

    execution = client.get("/api/maintenance/execution").json()
    survivor = next((row for row in execution if row["id"] == record_id), None)
    assert survivor is not None and survivor["plan_id"] == plan["id"]
    assert any(item["id"] == plan["id"] for item in client.get("/api/maintenance/plans").json())
    operations = client.get("/api/maintenance/operations").json()
    assert any(item["id"] == operation["id"] for item in operations)


def test_bulk_delete_allows_plan_with_only_scheduled_placeholder(api):
    client, ids = api
    plan, operation = _approve_plan_with_operation(
        client, ids["model_a"], plan_name="خطة جماعية بموعد"
    )
    scheduled = client.post(
        "/api/maintenance/execution",
        json={
            "equipment_id": ids["equipment_a"],
            "operation_id": operation["id"],
            "plan_id": plan["id"],
            "maintenance_date": "2026-10-12",
            "meter_value": 1000,
            "is_scheduled": True,
            "status": "scheduled",
        },
    )
    assert scheduled.status_code in (200, 201), scheduled.text
    record_id = scheduled.json()["id"]

    response = client.post(
        "/api/maintenance/plans/bulk-delete",
        json={"plan_ids": [plan["id"]]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["success"] == 1
    assert response.json()["rejected"] == []

    record = next(
        row for row in client.get("/api/maintenance/execution").json()
        if row["id"] == record_id
    )
    assert record["is_scheduled"] is True
    assert record["plan_id"] is None


def test_bulk_delete_rejects_empty_list(api):
    client, _ = api
    response = client.post("/api/maintenance/plans/bulk-delete", json={"plan_ids": []})
    assert response.status_code == 422


def test_bulk_delete_rejects_non_positive_ids(api):
    client, _ = api
    response = client.post("/api/maintenance/plans/bulk-delete", json={"plan_ids": [0, -3]})
    assert response.status_code == 422


def test_bulk_delete_rejects_duplicate_plan_ids(api):
    client, ids = api
    plan = _create_plan(client, ids["model_a"])
    response = client.post(
        "/api/maintenance/plans/bulk-delete",
        json={"plan_ids": [plan["id"], plan["id"]]},
    )
    assert response.status_code == 422
    assert any(item["id"] == plan["id"] for item in client.get("/api/maintenance/plans").json())


# ------------------------------------------------------------
# اختبارات إضافية لسيناريوهات الحذف المختلفة للعمليات
# ------------------------------------------------------------

def _create_operation_with_multiple_models(client, model_ids, name="عملية متعددة الطرازات"):
    """Create an operation linked to multiple equipment models."""
    conditions = [
        {"model_id": mid, "condition_source": "model", "interval_km": 10000}
        for mid in model_ids
    ]
    response = client.post(
        "/api/maintenance/operations",
        json={"name": name, "equipment_model_conditions": conditions},
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_bulk_delete_operations_reports_success_and_each_rejection(api):
    client, ids = api
    deletable = _create_operation(client, ids["model_a"], name="عملية قابلة للحذف")
    _, protected = _approve_plan_with_operation(
        client, ids["model_a"], plan_name="عملية محمية بخطة"
    )

    response = client.post(
        "/api/maintenance/bulk-delete",
        json={"operation_ids": [deletable["id"], protected["id"], 999999]},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["success"] == 1
    assert len(result["rejected"]) == 2
    assert all("operation_name" in item and item["reason"] for item in result["rejected"])
    assert "deleted" not in result
    assert "خطة" in next(
        item["reason"] for item in result["rejected"] if item["operation_id"] == protected["id"]
    )

    operations = client.get("/api/maintenance/operations").json()
    assert all(item["id"] != deletable["id"] for item in operations)
    assert any(item["id"] == protected["id"] for item in operations)


def test_bulk_delete_operations_rejects_invalid_payload(api):
    client, _ = api
    response = client.post("/api/maintenance/bulk-delete", json={"operation_ids": []})
    assert response.status_code == 422


def test_remove_operation_from_plan_keeps_operation_and_other_plans(api):
    """إزالة عملية من خطة: تحذف الارتباط فقط، وتبقي العملية والخطط الأخرى."""
    client, ids = api
    # Create two plans with the same operation
    plan1 = _create_plan(client, ids["model_a"], name="خطة 1")
    plan2 = _create_plan(client, ids["model_a"], name="خطة 2")
    operation = _create_operation(client, ids["model_a"], name="عملية مشتركة")

    # Add operation to both plans
    for plan in (plan1, plan2):
        linked = client.post(
            f"/api/maintenance/plans/{plan['id']}/operations",
            json={"plan_id": plan["id"], "operation_id": operation["id"], "sort_order": 1},
        )
        assert linked.status_code == 201, linked.text
    approved = client.post(f"/api/maintenance/plans/{plan1['id']}/approve")
    assert approved.status_code == 200, approved.text

    # Remove from plan1 only
    preview = client.get(f"/api/maintenance/plans/{plan1['id']}/operations/{operation['id']}/remove-impact")
    assert preview.status_code == 200, preview.text
    assert any(row["kind"] == "unlink" for row in preview.json()["effects"])
    assert any(row.get("kind") == "recalculate" and row["count"] == 1 for row in preview.json()["effects"])
    response = client.delete(
        f"/api/maintenance/plans/{plan1['id']}/operations/{operation['id']}"
    )
    assert response.status_code == 204, response.text

    # Operation still in plan2
    plan2_ops = client.get(f"/api/maintenance/plans/{plan2['id']}/operations").json()
    assert any(op["operation_id"] == operation["id"] for op in plan2_ops)

    # Operation still exists in library
    operations = client.get("/api/maintenance/operations").json()
    assert any(item["id"] == operation["id"] for item in operations)

    # plan1 no longer has the operation
    plan1_ops = client.get(f"/api/maintenance/plans/{plan1['id']}/operations").json()
    assert not any(op["operation_id"] == operation["id"] for op in plan1_ops)


def test_remove_operation_from_model_keeps_other_model_links(api):
    """إزالة عملية من طراز: تحذف ارتباط الطراز الحالي فقط، وتبقي ارتباطات الطرازات الأخرى."""
    client, ids = api
    equipment_type = EquipmentType(name="نوع اختبار", measurement_unit="km")
    # Create a second model
    db = Session()
    db.add(equipment_type)
    db.flush()
    model_b = EquipmentModel(name="طراز باء", equipment_type_id=equipment_type.id)
    db.add(model_b)
    db.flush()
    model_b_id = model_b.id
    db.commit()
    db.close()

    operation = _create_operation_with_multiple_models(client, [ids["model_a"], model_b_id])
    plan = _create_plan(client, ids["model_a"], name="خطة مرتبطة بالطراز")
    linked = client.post(
        f"/api/maintenance/plans/{plan['id']}/operations",
        json={"plan_id": plan["id"], "operation_id": operation["id"], "sort_order": 1},
    )
    assert linked.status_code == 201, linked.text
    approved = client.post(f"/api/maintenance/plans/{plan['id']}/approve")
    assert approved.status_code == 200, approved.text

    # Remove from model_a only
    preview = client.get(f"/api/maintenance/operations/{operation['id']}/models/{ids['model_a']}/remove-impact")
    assert preview.status_code == 200, preview.text
    assert any(row["kind"] == "unlink" for row in preview.json()["effects"])
    assert any(row.get("kind") == "recalculate" and row["count"] == 1 for row in preview.json()["effects"])
    response = client.delete(
        f"/api/maintenance/operations/{operation['id']}/models/{ids['model_a']}"
    )
    assert response.status_code == 204, response.text

    # Operation still linked to model_b
    models = client.get(f"/api/maintenance/operations/{operation['id']}/models").json()
    model_ids = [m["id"] for m in models]
    assert model_b_id in model_ids
    assert ids["model_a"] not in model_ids

    # Operation still exists in library
    operations = client.get("/api/maintenance/operations").json()
    assert any(item["id"] == operation["id"] for item in operations)


def test_remove_operation_from_model_keeps_execution_records(api):
    """إزالة عملية من طراز: لا تحذف سجلات التنفيذ التاريخية."""
    client, ids = api
    operation = _create_operation(client, ids["model_a"], name="عملية بسجل")
    plan, _ = _approve_plan_with_operation(client, ids["model_a"], plan_name="خطة للسجل")
    # The operation from _approve_plan_with_operation is different, use our operation
    # Add our operation to the plan
    linked = client.post(
        f"/api/maintenance/plans/{plan['id']}/operations",
        json={"plan_id": plan["id"], "operation_id": operation["id"], "sort_order": 2},
    )
    assert linked.status_code == 201, linked.text

    # Re-approve the plan after adding the operation
    approved = client.post(f"/api/maintenance/plans/{plan['id']}/approve")
    assert approved.status_code == 200, approved.text

    # Execute the plan with our operation
    executed = client.post(
        "/api/maintenance/plan-execution",
        json={
            "equipment_id": ids["equipment_a"],
            "plan_id": plan["id"],
            "operation_ids": [operation["id"]],
            "maintenance_date": str(date(2026, 9, 25)),
            "meter_value": 1000,
        },
    )
    assert executed.status_code in (200, 201), executed.text
    record_id = executed.json()[0]["id"]

    # Remove operation from model
    response = client.delete(
        f"/api/maintenance/operations/{operation['id']}/models/{ids['model_a']}"
    )
    assert response.status_code == 204, response.text

    # Execution record still exists
    execution = client.get("/api/maintenance/execution").json()
    survivor = next((row for row in execution if row["id"] == record_id), None)
    assert survivor is not None
    assert survivor["operation_id"] == operation["id"]


def test_removing_model_link_invalidates_only_approved_plans_for_that_model(api):
    client, ids = api
    db = Session()
    equipment_type = EquipmentType(name="نوع طراز ثانٍ", measurement_unit="km")
    db.add(equipment_type)
    db.flush()
    model_b = EquipmentModel(name="طراز باء لإبطال الاعتماد", equipment_type_id=equipment_type.id)
    db.add(model_b)
    db.commit()
    model_b_id = model_b.id
    db.close()

    shared = _create_operation_with_multiple_models(
        client, [ids["model_a"], model_b_id], name="عملية مشتركة للطرازين"
    )
    retained = _create_operation(client, ids["model_a"], name="عملية أخرى في الخطة")
    plan_a1 = _create_plan(client, ids["model_a"], name="خطة أ المعتمدة الأولى")
    plan_a2 = _create_plan(client, ids["model_a"], name="خطة أ المعتمدة الثانية")
    plan_a3 = _create_plan(client, ids["model_a"], name="خطة أ غير المعتمدة")
    plan_b = _create_plan(client, model_b_id, name="خطة ب غير متأثرة")

    def attach_and_approve(plan, operation, approve=True):
        linked = client.post(
            f"/api/maintenance/plans/{plan['id']}/operations",
            json={"plan_id": plan["id"], "operation_id": operation["id"], "sort_order": 1},
        )
        assert linked.status_code == 201, linked.text
        if approve:
            approved = client.post(f"/api/maintenance/plans/{plan['id']}/approve")
            assert approved.status_code == 200, approved.text

    attach_and_approve(plan_a1, shared, approve=False)
    attach_and_approve(plan_a1, retained, approve=False)
    approved = client.post(f"/api/maintenance/plans/{plan_a1['id']}/approve")
    assert approved.status_code == 200, approved.text
    attach_and_approve(plan_a2, shared)
    attach_and_approve(plan_a3, shared, approve=False)
    attach_and_approve(plan_b, shared)
    execution = client.post(
        "/api/maintenance/plan-execution",
        json={
            "equipment_id": ids["equipment_a"],
            "plan_id": plan_a1["id"],
            "operation_ids": [shared["id"]],
            "maintenance_date": "2026-09-25",
            "meter_value": 1000,
        },
    )
    assert execution.status_code == 201, execution.text
    record_id = execution.json()[0]["id"]

    response = client.delete(
        f"/api/maintenance/operations/{shared['id']}/models/{ids['model_a']}"
    )
    assert response.status_code == 204, response.text

    plans = {row["id"]: row for row in client.get("/api/maintenance/plans").json()}
    assert plans[plan_a1["id"]]["is_approved"] is False
    assert plans[plan_a2["id"]]["is_approved"] is False
    assert plans[plan_a3["id"]]["is_approved"] is False
    assert plans[plan_b["id"]]["is_approved"] is True

    models = client.get(f"/api/maintenance/operations/{shared['id']}/models").json()
    assert [model["id"] for model in models] == [model_b_id]
    operations = client.get("/api/maintenance/operations").json()
    assert {shared["id"], retained["id"]}.issubset({item["id"] for item in operations})
    record = next(
        row for row in client.get("/api/maintenance/execution").json()
        if row["id"] == record_id
    )
    assert record["plan_id"] == plan_a1["id"]
    assert record["operation_id"] == shared["id"]


def test_removing_operation_from_approved_plan_unapproves_plan_only(api):
    client, ids = api
    plan, operation = _approve_plan_with_operation(client, ids["model_a"])
    other_plan, _ = _approve_plan_with_operation(
        client, ids["model_a"], plan_name="خطة أخرى معتمدة"
    )
    record = _execute_plan(client, ids["equipment_a"], plan, operation)[0]

    response = client.delete(
        f"/api/maintenance/plans/{plan['id']}/operations/{operation['id']}"
    )
    assert response.status_code == 204, response.text
    plans = {row["id"]: row for row in client.get("/api/maintenance/plans").json()}
    assert plans[plan["id"]]["is_approved"] is False
    assert plans[other_plan["id"]]["is_approved"] is True
    assert client.get(f"/api/maintenance/plans/{plan['id']}/operations").json() == []
    assert any(
        row["id"] == record["id"]
        for row in client.get("/api/maintenance/execution").json()
    )


def test_delete_operation_from_library_when_unlinked_succeeds(api):
    """حذف عملية من المكتبة: ينجح إذا كانت غير مرتبطة بأي خطة أو سجل."""
    client, ids = api
    operation = _create_operation(client, ids["model_a"], name="عملية للحذف")

    response = client.delete(f"/api/maintenance/operations/{operation['id']}")
    assert response.status_code == 204, response.text

    operations = client.get("/api/maintenance/operations").json()
    assert not any(item["id"] == operation["id"] for item in operations)


def test_delete_operation_from_library_with_plan_link_rejected(api):
    """حذف عملية من المكتبة: يرفض بخطأ 409 إذا كانت مرتبطة بخطة."""
    client, ids = api
    plan, operation = _approve_plan_with_operation(client, ids["model_a"])

    response = client.delete(f"/api/maintenance/operations/{operation['id']}")
    assert response.status_code == 409
    body = response.json()
    assert "خطة" in body["detail"]
    assert "ارتبط" in body["detail"] or "مرتبطة" in body["detail"]

    # Operation still exists
    operations = client.get("/api/maintenance/operations").json()
    assert any(item["id"] == operation["id"] for item in operations)


def test_delete_operation_from_library_with_record_rejected(api):
    """حذف عملية من المكتبة: يرفض بخطأ 409 إذا كانت مستخدمة في سجل صيانة.

    ملاحظة: الترتيب الحالي في الخادم يفحص ارتباط الخطة أولاً، لذا عند وجود سجل
    تنفيذ للخطة، سيرفض بسبب ارتباط الخطة. هذا سلوك مقبول.
    """
    client, ids = api
    plan, operation = _approve_plan_with_operation(client, ids["model_a"])
    _execute_plan(client, ids["equipment_a"], plan, operation)

    response = client.delete(f"/api/maintenance/operations/{operation['id']}")
    assert response.status_code == 409
    body = response.json()
    # يفحص ارتباط الخطة أولاً (لأن الخطة تحتوي العملية)
    assert "خطة" in body["detail"]

    # Operation still exists
    operations = client.get("/api/maintenance/operations").json()
    assert any(item["id"] == operation["id"] for item in operations)


def test_delete_operation_returns_204_no_content_handled_correctly(api):
    """استجابة 204 No Content: الواجهة لا تحاول تحليل JSON وتعتبر العملية ناجحة."""
    client, ids = api
    operation = _create_operation(client, ids["model_a"], name="عملية 204")

    response = client.delete(f"/api/maintenance/operations/{operation['id']}")
    assert response.status_code == 204
    assert response.content == b""


def test_delete_plan_returns_204_no_content_handled_correctly(api):
    """استجابة 204 No Content لحذف الخطة: الواجهة لا تحاول تحليل JSON."""
    client, ids = api
    plan = _create_plan(client, ids["model_a"], name="خطة 204")

    response = client.delete(f"/api/maintenance/plans/{plan['id']}")
    assert response.status_code == 204
    assert response.content == b""


def test_delete_plan_operation_returns_204_no_content(api):
    """استجابة 204 No Content لإزالة عملية من خطة."""
    client, ids = api
    plan, operation = _approve_plan_with_operation(client, ids["model_a"])

    response = client.delete(
        f"/api/maintenance/plans/{plan['id']}/operations/{operation['id']}"
    )
    assert response.status_code == 204
    assert response.content == b""


def test_remove_operation_model_returns_204_no_content(api):
    """استجابة 204 No Content لإزالة عملية من طراز."""
    client, ids = api
    operation = _create_operation(client, ids["model_a"], name="عملية إزالة طراز")

    response = client.delete(
        f"/api/maintenance/operations/{operation['id']}/models/{ids['model_a']}"
    )
    assert response.status_code == 204
    assert response.content == b""


def test_delete_missing_operation_returns_404(api):
    """حذف عملية غير موجودة: يعيد 404 مع رسالة واضحة."""
    client, _ = api
    response = client.delete("/api/maintenance/operations/999999")
    assert response.status_code == 404
    assert response.json()["detail"] == "عملية الصيانة غير موجودة."


def test_delete_missing_model_link_returns_404(api):
    """إزالة ارتباط عملية-طراز غير موجود: يعيد 404."""
    client, ids = api
    operation = _create_operation(client, ids["model_a"])

    response = client.delete(f"/api/maintenance/operations/{operation['id']}/models/999999")
    assert response.status_code == 404
    assert "طراز" in response.json()["detail"]


def test_error_response_structure_contains_detail_field(api):
    """استجابات الخطأ (404, 409, 422) تحتوي على حقل detail قابل للعرض."""
    client, ids = api
    operation = _create_operation(client, ids["model_a"])

    # 404 - missing operation
    resp = client.delete("/api/maintenance/operations/999999")
    assert resp.status_code == 404
    assert "detail" in resp.json()

    # 409 - plan link
    plan, op = _approve_plan_with_operation(client, ids["model_a"])
    resp = client.delete(f"/api/maintenance/operations/{op['id']}")
    assert resp.status_code == 409
    assert "detail" in resp.json()

    # 409 - record link
    _execute_plan(client, ids["equipment_a"], plan, op)
    resp = client.delete(f"/api/maintenance/operations/{op['id']}")
    assert resp.status_code == 409
    assert "detail" in resp.json()

    # 422 - validation error
    resp = client.post("/api/maintenance/plans/bulk-delete", json={"plan_ids": []})
    assert resp.status_code == 422


def test_bulk_plan_operation_add_keeps_compatible_items_and_reports_each_rejection(api):
    client, ids = api
    plan = _create_plan(client, ids["model_a"])
    operation = client.post(
        "/api/maintenance/operations",
        json={
            "name": "عملية دفعة",
            "equipment_model_conditions": [
                {"model_id": ids["model_a"], "condition_source": "model", "interval_km": 900}
            ],
        },
    )
    assert operation.status_code == 201, operation.text
    operation_id = operation.json()["id"]
    second_operation = client.post("/api/maintenance/operations", json={"name": "عملية دفعة ثانية"})
    assert second_operation.status_code == 201, second_operation.text
    second_operation_id = second_operation.json()["id"]

    invalid = client.post(
        f"/api/maintenance/plans/{plan['id']}/operations/bulk",
        json={"operation_ids": [operation_id, 999999]},
    )
    assert invalid.status_code == 201, invalid.text
    assert invalid.json()["success"] == 1
    assert [item["operation_id"] for item in invalid.json()["added"]] == [operation_id]
    assert invalid.json()["rejected"] == [{
        "source": "general", "operation_id": 999999,
        "operation_name": "#999999", "reason": "عملية الصيانة غير موجودة.",
    }]

    added = client.post(
        f"/api/maintenance/plans/{plan['id']}/operations/bulk",
        json={"operation_ids": [operation_id, second_operation_id]},
    )
    assert added.status_code == 201, added.text
    assert added.json()["success"] == 1
    assert [link["operation_id"] for link in added.json()["added"]] == [second_operation_id]
    assert len(added.json()["rejected"]) == 1
    assert "مرتبطة بهذه الخطة مسبقًا" in added.json()["rejected"][0]["reason"]

    duplicate = client.post(
        f"/api/maintenance/plans/{plan['id']}/operations/bulk",
        json={"operation_ids": [operation_id]},
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["success"] == 0
    assert "مرتبطة بهذه الخطة مسبقًا" in duplicate.json()["rejected"][0]["reason"]
    links = client.get(f"/api/maintenance/plans/{plan['id']}/operations").json()
    assert [link["operation_id"] for link in links] == [operation_id, second_operation_id]
    stored_operation = next(item for item in client.get("/api/maintenance/operations").json() if item["id"] == operation_id)
    stored_condition = next(item for item in stored_operation["model_conditions"] if item["model_id"] == ids["model_a"])
    assert float(stored_condition["interval_km"]) == 900


def test_private_model_operation_is_separate_and_plans_enforce_model_and_condition(api):
    client, ids = api
    private = client.post("/api/maintenance/model-operations", json={
        "name": "عملية مستوردة خاصة بالطراز أ",
        "equipment_model_id": ids["model_a"],
        "interval_km": 15000,
    })
    assert private.status_code == 201, private.text
    operation_id = private.json()["id"]

    general_library_ids = {item["id"] for item in client.get("/api/maintenance/operations").json()}
    model_a_library_ids = {
        item["id"] for item in client.get(
            f"/api/maintenance/model-operations?equipment_model_id={ids['model_a']}"
        ).json()
    }
    model_b_library_ids = {
        item["id"] for item in client.get(
            f"/api/maintenance/model-operations?equipment_model_id={ids['model_b']}"
        ).json()
    }
    assert operation_id not in general_library_ids
    assert operation_id in model_a_library_ids
    assert operation_id not in model_b_library_ids

    plan_a = _create_plan(client, ids["model_a"], name="خطة الطراز أ")
    plan_b = _create_plan(client, ids["model_b"], name="خطة الطراز ب")
    rejected = client.post(
        f"/api/maintenance/plans/{plan_b['id']}/operations",
        json={"plan_id": plan_b["id"], "model_operation_id": operation_id, "sort_order": 1},
    )
    assert rejected.status_code == 409
    assert client.get(f"/api/maintenance/plans/{plan_b['id']}/operations").json() == []

    mismatched = client.post(
        f"/api/maintenance/plans/{plan_a['id']}/operations",
        json={"plan_id": plan_a["id"], "model_operation_id": operation_id, "sort_order": 1},
    )
    assert mismatched.status_code == 409
    assert "لا يطابق شرط الخطة" in mismatched.json()["detail"]

    general = client.post("/api/maintenance/operations", json={"name": "عملية عامة صالحة"})
    assert general.status_code == 201, general.text
    accepted = client.post(
        f"/api/maintenance/plans/{plan_a['id']}/operations",
        json={"plan_id": plan_a["id"], "model_operation_id": operation_id, "sort_order": 1},
    )
    # تبقى الخطة أ غير قابلة لاستقبال هذا الشرط المختلف؛ أضف شرطًا مطابقًا لعملية خاصة أخرى.
    assert accepted.status_code == 409

    matching = client.post("/api/maintenance/model-operations", json={
        "name": "عملية خاصة متوافقة",
        "equipment_model_id": ids["model_a"],
        "interval_km": 10000,
    })
    assert matching.status_code == 201, matching.text

    bulk = client.post(
        f"/api/maintenance/plans/{plan_a['id']}/operations/bulk",
        json={"operation_ids": [general.json()["id"]], "model_operation_ids": [operation_id, matching.json()["id"]]},
    )
    assert bulk.status_code == 201, bulk.text
    assert bulk.json()["success"] == 2
    assert {item["source"] for item in bulk.json()["added"]} == {"general", "model"}
    assert len(bulk.json()["rejected"]) == 1
    assert bulk.json()["rejected"][0]["operation_id"] == operation_id
    assert "لا يطابق شرط الخطة" in bulk.json()["rejected"][0]["reason"]
    assert {link["source"] for link in client.get(f"/api/maintenance/plans/{plan_a['id']}/operations").json()} == {"general", "model"}


def test_private_operation_editor_and_plan_keep_all_condition_axes(api):
    client, ids = api
    operation_payload = {
        "name": "تغيير الزيت وفق أقرب فاصل",
        "equipment_model_id": ids["model_a"],
        "interval_km": 12000,
        "interval_days": 183,
    }
    created = client.post("/api/maintenance/model-operations", json=operation_payload)
    assert created.status_code == 201, created.text
    operation_id = created.json()["id"]
    assert float(created.json()["interval_km"]) == 12000
    assert created.json()["interval_days"] == 183

    listed = client.get(f"/api/maintenance/model-operations?equipment_model_id={ids['model_a']}")
    assert listed.status_code == 200, listed.text
    stored = next(row for row in listed.json() if row["id"] == operation_id)
    assert float(stored["interval_km"]) == 12000
    assert stored["interval_days"] == 183

    plan_response = client.post("/api/maintenance/plans", json={
        "name": "خطة بأقرب فاصل",
        "equipment_model_id": ids["model_a"],
        "interval_km": 12000,
        "interval_days": 183,
    })
    assert plan_response.status_code == 201, plan_response.text
    plan = plan_response.json()
    added = client.post(
        f"/api/maintenance/plans/{plan['id']}/operations",
        json={"plan_id": plan["id"], "model_operation_id": operation_id},
    )
    assert added.status_code == 201, added.text

    # Editing both axes retains the exact condition required by its plan.
    updated = client.put(f"/api/maintenance/model-operations/{operation_id}", json={
        **operation_payload,
        "description": "التغيير عند تحقق أي من الفاصلين",
        "warning_km": 1000,
        "warning_days": 30,
    })
    assert updated.status_code == 200, updated.text
    assert float(updated.json()["interval_km"]) == 12000
    assert updated.json()["interval_days"] == 183
    assert float(updated.json()["warning_km"]) == 1000
    assert updated.json()["warning_days"] == 30

    conflicting = client.put(f"/api/maintenance/model-operations/{operation_id}", json={
        **operation_payload,
        "interval_days": 180,
    })
    assert conflicting.status_code == 409
    assert "لا يطابق شرط الخطة" in conflicting.json()["detail"]


def test_private_plan_operation_is_shown_and_recorded_in_execution_history(api):
    client, ids = api
    operation = client.post("/api/maintenance/model-operations", json={
        "name": "تغيير زيت المحرك للطراز",
        "equipment_model_id": ids["model_a"],
        "interval_km": 10000,
        "warning_km": 500,
    })
    assert operation.status_code == 201, operation.text
    operation_id = operation.json()["id"]
    plan = _create_plan(client, ids["model_a"], name="خطة عمليات الطراز")

    added = client.post(
        f"/api/maintenance/plans/{plan['id']}/operations",
        json={"plan_id": plan["id"], "model_operation_id": operation_id},
    )
    assert added.status_code == 201, added.text
    assert added.json()["source"] == "model"
    assert added.json()["operation_name"] == "تغيير زيت المحرك للطراز"

    approved = client.post(f"/api/maintenance/plans/{plan['id']}/approve")
    assert approved.status_code == 200, approved.text
    recorded = client.post("/api/maintenance/plan-execution", json={
        "equipment_id": ids["equipment_a"],
        "plan_id": plan["id"],
        "model_operation_ids": [operation_id],
        "maintenance_date": str(date.today()),
        "meter_value": 1000,
    })
    assert recorded.status_code == 201, recorded.text
    assert len(recorded.json()) == 1
    assert recorded.json()[0]["operation_id"] is None
    assert recorded.json()[0]["model_operation_id"] == operation_id

    edit_page = client.get(f"/maintenance/records?edit={recorded.json()[0]['id']}")
    assert edit_page.status_code == 200, edit_page.text
    assert f'value="model:{operation_id}"' in edit_page.text
    assert "تغيير زيت المحرك للطراز — عملية خاصة بالطراز" in edit_page.text


def test_standalone_model_condition_is_separate_from_plan_condition(api):
    client, ids = api
    plan = _create_plan(client, ids["model_a"])
    operation_response = client.post("/api/maintenance/operations", json={"name": "عملية مستقلة وخطة"})
    assert operation_response.status_code == 201, operation_response.text
    operation_id = operation_response.json()["id"]
    linked = client.post(
        f"/api/maintenance/plans/{plan['id']}/operations",
        json={"plan_id": plan["id"], "operation_id": operation_id},
    )
    assert linked.status_code == 201, linked.text

    condition_url = f"/api/maintenance/operations/{operation_id}/models/{ids['model_a']}/condition"
    saved = client.post(condition_url, json={"interval_km": 1200})
    assert saved.status_code == 201, saved.text
    duplicate = client.post(condition_url, json={"interval_days": 30})
    assert duplicate.status_code == 409
    assert client.post(condition_url, json={"interval_km": -1}).status_code == 422
    assert client.post(condition_url, json={"interval_km": 0}).status_code == 422
    assert client.post(condition_url, json={"unit": "months", "interval_days": 30}).status_code == 422
    duplicate_bulk = client.post(
        f"/api/maintenance/plans/{plan['id']}/operations/bulk",
        json={"operation_ids": [operation_id]},
    )
    assert duplicate_bulk.status_code == 201, duplicate_bulk.text
    assert duplicate_bulk.json()["success"] == 0
    assert "مرتبطة بهذه الخطة مسبقًا" in duplicate_bulk.json()["rejected"][0]["reason"]

    updated_plan = client.put(
        f"/api/maintenance/plans/{plan['id']}",
        json={
            "name": plan["name"],
            "equipment_model_id": ids["model_a"],
            "interval_km": 25000,
            "is_active": True,
            "description": plan.get("description"),
        },
    )
    assert updated_plan.status_code == 200, updated_plan.text
    operation = next(item for item in client.get("/api/maintenance/operations").json() if item["id"] == operation_id)
    model_condition = next(item for item in operation["model_conditions"] if item["model_id"] == ids["model_a"])
    assert float(model_condition["interval_km"]) == 1200
    assert client.get(f"/api/maintenance/plans/{plan['id']}/operations").json()[0]["operation_id"] == operation_id

    edited = client.patch(condition_url, json={"interval_hours": 75})
    assert edited.status_code == 200, edited.text
    operation = next(item for item in client.get("/api/maintenance/operations").json() if item["id"] == operation_id)
    model_condition = next(item for item in operation["model_conditions"] if item["model_id"] == ids["model_a"])
    assert model_condition["interval_km"] is None
    assert float(model_condition["interval_hours"]) == 75
    assert client.get(f"/api/maintenance/plans/{plan['id']}/operations").json()[0]["operation_id"] == operation_id
