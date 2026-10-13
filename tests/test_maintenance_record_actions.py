"""حماية سجل التنفيذ وإجراءات سجل الصيانة.

يحذف موعدًا مجدولًا غير منفذ فقط؛ سجل التنفيذ الفعلي وتاريخه محميان.
"""

from datetime import date
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.dependencies import get_current_user
from app.core.config import settings
from app.database import session as session_module
from app.database.base import Base
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentModel, EquipmentType
from app.modules.maintenance.models import MaintenanceOperation, MaintenancePlan, MaintenanceRecord
from app.modules.maintenance.router import router as maintenance_router
from app.modules.meter_readings.models import MeterReading
from app.modules.users.models import User

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
Session = sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture()
def api():
    """واجهة REST حقيقية على قاعدة مؤقتة معزولة."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    seed = Session()
    equipment_type = EquipmentType(name="نوع اختبار سجل الصيانة", measurement_unit="km")
    seed.add(equipment_type)
    seed.flush()
    model_a = EquipmentModel(name="طراز سجلات", equipment_type_id=equipment_type.id)
    seed.add(model_a)
    seed.flush()
    equipment_a = Equipment(
        asset_code="REC-DELETE-A",
        registration_number="REC-DELETE-A",
        equipment_type_id=equipment_type.id,
        equipment_model_id=model_a.id,
    )
    seed.add(equipment_a)
    seed.add(User(id=1, username="record-delete-admin", full_name="مسؤول", hashed_password="x", role="admin", is_active=True))
    seed.commit()
    ids = {"model_a": model_a.id, "equipment_a": equipment_a.id}
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
        return User(id=1, username="record-delete-admin", full_name="مسؤول", hashed_password="x", role="admin", is_active=True)

    app.dependency_overrides[session_module.get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    with TestClient(app) as client:
        yield client, ids


def _create_operation(client, model_id, name="عملية للحذف", interval_km=10000):
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


def _create_plan(client, model_id, name="خطة للحذف"):
    response = client.post(
        "/api/maintenance/plans",
        json={"name": name, "equipment_model_id": model_id, "interval_km": 10000},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _approve_plan_with_operation(client, model_id, plan_name="خطة معتمدة"):
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


def _current_odometer(equipment_id):
    db = Session()
    try:
        return float(db.get(Equipment, equipment_id).current_odometer)
    finally:
        db.close()


def _create_record(
    client,
    equipment_id,
    operation_id,
    plan_id=None,
    maintenance_date=None,
    meter_value=1000,
    is_scheduled=False,
    status="completed",
):
    """Create a maintenance record via the API."""
    if maintenance_date is None:
        maintenance_date = date(2026, 9, 25)
    payload = {
        "equipment_id": equipment_id,
        "operation_id": operation_id,
        "maintenance_date": str(maintenance_date),
        "meter_value": meter_value,
        "is_scheduled": is_scheduled,
        "status": status,
        "description": "اختبار الحذف",
        "note": "ملاحظة",
    }
    if plan_id:
        payload["plan_id"] = plan_id
    response = client.post("/api/maintenance/execution", json=payload)
    assert response.status_code in (200, 201), response.text
    return response.json()


def test_delete_record_keeps_operation_and_plan(api):
    """حذف موعد غير منفذ يبقي العملية والخطة."""
    client, ids = api
    plan, operation = _approve_plan_with_operation(client, ids["model_a"])
    record = _create_record(
        client, ids["equipment_a"], operation["id"], plan["id"],
        is_scheduled=True, status="scheduled",
    )
    record_id = record["id"]

    # Delete via API
    deleted = client.delete(f"/api/maintenance/records/{record_id}")
    assert deleted.status_code == 204, deleted.text
    assert deleted.content == b""

    # Record gone
    execution = client.get("/api/maintenance/execution").json()
    assert not any(row["id"] == record_id for row in execution)

    # Operation still exists
    operations = client.get("/api/maintenance/operations").json()
    assert any(item["id"] == operation["id"] for item in operations)

    # Plan still exists
    plans = client.get("/api/maintenance/plans").json()
    assert any(item["id"] == plan["id"] for item in plans)


def test_delete_record_without_plan_keeps_operation(api):
    """حذف موعد مستقل غير منفذ يبقي العملية."""
    client, ids = api
    operation = _create_operation(client, ids["model_a"], name="عملية مستقلة للحذف")
    record = _create_record(
        client, ids["equipment_a"], operation["id"],
        is_scheduled=True, status="scheduled",
    )
    record_id = record["id"]

    deleted = client.delete(f"/api/maintenance/records/{record_id}")
    assert deleted.status_code == 204, deleted.text

    execution = client.get("/api/maintenance/execution").json()
    assert not any(row["id"] == record_id for row in execution)

    operations = client.get("/api/maintenance/operations").json()
    assert any(item["id"] == operation["id"] for item in operations)


def test_delete_missing_record_returns_404(api):
    """حذف سجل غير موجود: يعيد 404 مع رسالة واضحة."""
    client, _ = api
    response = client.delete("/api/maintenance/records/999999")
    assert response.status_code == 404
    assert response.json()["detail"] == "سجل الصيانة غير موجود."


def test_delete_record_returns_204_no_content(api):
    """استجابة الحذف المسموح 204 بلا جسم أو Content-Type."""
    client, ids = api
    plan, operation = _approve_plan_with_operation(client, ids["model_a"])
    record = _create_record(
        client, ids["equipment_a"], operation["id"], plan["id"],
        is_scheduled=True, status="scheduled",
    )

    response = client.delete(f"/api/maintenance/records/{record['id']}")
    assert response.status_code == 204
    assert response.content == b""
    assert response.headers.get("content-type") is None


def test_delete_record_preserves_other_records_of_same_operation(api):
    """حذف سجل واحد: لا يؤثر في سجلات أخرى لنفس العملية."""
    client, ids = api
    plan, operation = _approve_plan_with_operation(client, ids["model_a"])

    # Create two records on different dates
    record1 = _create_record(
        client, ids["equipment_a"], operation["id"], plan["id"], date(2026, 9, 25),
        is_scheduled=True, status="scheduled",
    )
    record2 = _create_record(client, ids["equipment_a"], operation["id"], plan["id"], date(2026, 9, 26))
    record1_id = record1["id"]
    record2_id = record2["id"]

    # Delete only the first
    deleted = client.delete(f"/api/maintenance/records/{record1_id}")
    assert deleted.status_code == 204

    execution = client.get("/api/maintenance/execution").json()
    remaining = [row for row in execution if row["operation_id"] == operation["id"]]
    assert len(remaining) == 1
    assert remaining[0]["id"] == record2_id


def test_delete_record_preserves_other_records_of_same_equipment(api):
    """حذف سجل واحد: لا يؤثر في سجلات أخرى لنفس العتاد."""
    client, ids = api
    plan, operation = _approve_plan_with_operation(client, ids["model_a"])
    operation2 = _create_operation(client, ids["model_a"], name="عملية ثانية")

    # Add operation2 to the plan
    linked = client.post(
        f"/api/maintenance/plans/{plan['id']}/operations",
        json={"plan_id": plan["id"], "operation_id": operation2["id"], "sort_order": 2},
    )
    assert linked.status_code == 201, linked.text
    # Re-approve plan after adding operation
    approved = client.post(f"/api/maintenance/plans/{plan['id']}/approve")
    assert approved.status_code == 200, approved.text

    # Create two records with different operations on different dates
    record1 = _create_record(
        client, ids["equipment_a"], operation["id"], plan["id"], date(2026, 9, 25),
        is_scheduled=True, status="scheduled",
    )
    record2 = _create_record(client, ids["equipment_a"], operation2["id"], plan["id"], date(2026, 9, 26))
    record1_id = record1["id"]

    deleted = client.delete(f"/api/maintenance/records/{record1_id}")
    assert deleted.status_code == 204

    execution = client.get("/api/maintenance/execution").json()
    remaining = [row for row in execution if row["equipment_id"] == ids["equipment_a"]]
    assert len(remaining) == 1
    assert remaining[0]["id"] == record2["id"]


def test_actual_execution_cannot_be_deleted_or_change_equipment_meter(api):
    """رفض حذف التنفيذ يحمي السجل وقيمة العداد المشتقة منه."""
    client, ids = api
    plan, operation = _approve_plan_with_operation(client, ids["model_a"])
    record = _create_record(client, ids["equipment_a"], operation["id"], plan["id"])
    record_id = record["id"]

    deleted = client.delete(f"/api/maintenance/records/{record_id}")
    assert deleted.status_code == 409
    assert "تاريخ" in deleted.json()["detail"]

    execution = client.get("/api/maintenance/execution").json()
    assert any(row["id"] == record_id for row in execution)

    assert _current_odometer(ids["equipment_a"]) == 1000


def test_html_delete_route_uses_the_same_protection(api):
    client, ids = api
    plan, operation = _approve_plan_with_operation(client, ids["model_a"])
    record = _create_record(client, ids["equipment_a"], operation["id"], plan["id"])

    response = client.post(
        f"/maintenance/records/{record['id']}/delete",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "error=protected_record" in response.headers["location"]
    assert any(row["id"] == record["id"] for row in client.get("/api/maintenance/execution").json())


def test_bulk_delete_reports_mixed_safe_and_protected_records(api):
    client, ids = api
    plan, operation = _approve_plan_with_operation(client, ids["model_a"])
    scheduled = _create_record(
        client, ids["equipment_a"], operation["id"], plan["id"], date(2026, 9, 25),
        is_scheduled=True, status="scheduled",
    )
    actual = _create_record(
        client, ids["equipment_a"], operation["id"], plan["id"], date(2026, 9, 26),
    )

    response = client.post(
        "/api/maintenance/records/bulk-delete",
        json={"record_ids": [scheduled["id"], actual["id"], 999999]},
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["success"] == 1
    assert result["deleted_ids"] == [scheduled["id"]]
    assert [(item["record_id"], item["reason"]) for item in result["rejected"]] == [
        (actual["id"], "لا يمكن حذف سجل تنفيذ فعلي حفاظًا على التاريخ التشغيلي."),
        (999999, "سجل الصيانة غير موجود."),
    ]
    rows = client.get("/api/maintenance/execution").json()
    assert [row["id"] for row in rows] == [actual["id"]]


def test_bulk_delete_rejects_invalid_requests_without_changing_records(api):
    client, ids = api
    plan, operation = _approve_plan_with_operation(client, ids["model_a"])
    scheduled = _create_record(
        client, ids["equipment_a"], operation["id"], plan["id"],
        is_scheduled=True, status="scheduled",
    )

    response = client.post("/api/maintenance/records/bulk-delete", json={"record_ids": []})
    assert response.status_code == 422
    assert any(row["id"] == scheduled["id"] for row in client.get("/api/maintenance/execution").json())


def test_viewer_can_view_record_details_but_cannot_edit_or_delete(api, monkeypatch):
    client, ids = api
    _, operation = _approve_plan_with_operation(client, ids["model_a"])
    record = _create_record(
        client,
        ids["equipment_a"],
        operation["id"],
        is_scheduled=True,
        status="scheduled",
    )
    viewer = User(
        id=2,
        username="record-viewer",
        full_name="قارئ",
        hashed_password="x",
        role="viewer",
        is_active=True,
    )
    monkeypatch.setattr(settings, "DEV_DISABLE_AUTH", False)
    client.app.dependency_overrides[get_current_user] = lambda: viewer

    page = client.get("/maintenance/records")
    assert page.status_code == 200
    assert 'data-action-toggle="record-menu-' in page.text
    assert 'data-menu-action="record-details"' in page.text
    assert 'data-menu-action="record-edit"' not in page.text
    assert 'data-menu-action="record-delete"' not in page.text
    assert 'id="selectAllRecords"' not in page.text
    assert 'id="bulkDeleteRecords"' not in page.text

    individual = client.delete(f"/api/maintenance/records/{record['id']}")
    assert individual.status_code == 403
    bulk = client.post(
        "/api/maintenance/records/bulk-delete",
        json={"record_ids": [record["id"]]},
    )
    assert bulk.status_code == 403
    update = client.post(
        f"/maintenance/records/{record['id']}/update",
        data={
            "equipment_id": ids["equipment_a"],
            "operation_id": operation["id"],
            "maintenance_date": "2026-10-12",
            "meter_value": "",
        },
    )
    assert update.status_code == 403
    assert any(
        row["id"] == record["id"]
        for row in client.get("/api/maintenance/execution").json()
    )


def test_delete_scheduled_record_preserves_meter_history_and_current_value(api):
    client, ids = api
    plan, operation = _approve_plan_with_operation(client, ids["model_a"])
    db = Session()
    db.add_all([
        MeterReading(
            equipment_id=ids["equipment_a"],
            reading_date=datetime(2026, 9, 24, tzinfo=timezone.utc),
            odometer=900,
            hours=None,
        ),
        MeterReading(
            equipment_id=ids["equipment_a"],
            reading_date=datetime(2026, 9, 27, tzinfo=timezone.utc),
            odometer=1200,
            hours=None,
        ),
    ])
    db.commit()
    db.close()
    scheduled = _create_record(
        client, ids["equipment_a"], operation["id"], plan["id"], date(2026, 9, 26),
        meter_value=1100, is_scheduled=True, status="scheduled",
    )
    before = _current_odometer(ids["equipment_a"])

    deleted = client.delete(f"/api/maintenance/records/{scheduled['id']}")

    assert deleted.status_code == 204
    assert _current_odometer(ids["equipment_a"]) == before == 1200
    db = Session()
    assert db.query(MeterReading).filter(MeterReading.equipment_id == ids["equipment_a"]).count() == 2
    db.close()


def test_records_table_exposes_row_actions_and_bulk_selection():
    template = Path("app/modules/maintenance/templates/maintenance_records.html").read_text(encoding="utf-8")
    assert 'id="selectAllRecords"' in template
    assert 'class="record-check"' in template
    assert 'id="recordsBulkBar"' in template
    assert 'id="recordsSelectedCount"' in template
    assert 'id="bulkDeleteRecords"' in template
    assert "{% if can_manage_records %}" in template
    assert "{% if edit_record and can_manage_records %}" in template
    assert 'data-menu-action="record-edit"' in template
    assert "can_manage_records and r.is_scheduled and r.status == 'scheduled'" in template
    assert 'data-menu-action="record-delete"' in template
    assert "visibleRecordRows()" in template
    assert "result.success" in template
    assert "result.rejected" in template
    assert "response.ok" in template
    assert "finally{" in template
    assert "سيتم حذف الموعد المجدول غير المنفذ فقط" in template
    assert 'data-menu-action="record-details"' in template
    assert 'class="record-operation-cell"' in template
    assert '<th>الإجراءات</th>' not in template
    assert 'class="record-details-row" data-mt-filter-auxiliary hidden' in template
    assert '"record-details":()=>{' in template
    assert "can_manage_records and r.operation_id" in template
    assert "can_manage_records and r.is_scheduled and r.status == 'scheduled'" in template
    assert 'class="record-check"' in template  # Per-row and bulk selection stays available.


def test_new_record_form_is_available_from_a_dialog_triggered_by_toolbar():
    template = Path("app/modules/maintenance/templates/maintenance_records.html").read_text(encoding="utf-8")
    assert 'data-open-record-dialog' in template
    assert 'id="newRecordDialog"' in template
    assert 'id="maintenanceRecordForm"' in template
    assert 'data-close-record-dialog' in template
    assert 'recordDialog?.showModal()' in template


def test_unapproved_models_open_a_list_linking_to_plan_setup(api):
    client, ids = api
    response = client.get("/maintenance/due")

    assert response.status_code == 200
    assert 'id="unapprovedModelsDialog"' in response.text
    assert 'id="openUnapprovedModels"' in response.text
    assert "طراز سجلات" in response.text
    assert f"/maintenance/plans?model_id={ids['model_a']}&amp;new=1" in response.text
    assert "dialog.showModal();document.getElementById('openUnapprovedModels')" not in response.text
    assert "addEventListener('click',()=>dialog.showModal())" in response.text
    assert "لا توجد صيانة مستحقة لأن الصيانة لم تُبرمج لهذه الطرازات بعد" in response.text
    plans = client.get(f"/maintenance/plans?model_id={ids['model_a']}&new=1")
    assert plans.status_code == 200
    assert "startupParams.get('model_id')" in plans.text
    assert "startupParams.get('new')==='1'" in plans.text


def test_records_page_shows_due_maintenance_count(api):
    client, ids = api
    _create_operation(client, ids["model_a"], name="عملية مستحقة")

    response = client.get("/maintenance/records")

    assert response.status_code == 200
    assert "الصيانة المستحقة (1)" in response.text
    assert 'id="openUnapprovedModels"' in response.text
    assert 'id="unapprovedModelsDialog"' in response.text
    assert "openUnapprovedModels')?.addEventListener('click',()=>unapprovedModelsDialog?.showModal())" in response.text
    assert f"/maintenance/plans?model_id={ids['model_a']}&amp;new=1" in response.text
    assert 'href="/maintenance/due"' in response.text
    assert 'id="selectAllRecords"' in response.text


def test_record_bulk_delete_route_is_registered():
    from app.modules.maintenance.router import router

    assert any(
        getattr(route, "path", None) == "/api/maintenance/records/bulk-delete"
        and "POST" in (route.methods or set())
        for route in router.routes
    )
