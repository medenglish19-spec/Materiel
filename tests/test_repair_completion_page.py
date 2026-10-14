import re
from pathlib import Path
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.database import model_registry  # noqa: F401
from app.database import session as session_module
from app.database.base import Base
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentModel, EquipmentType
from app.modules.faults_repairs.models import Fault, Repair, TechnicianIntervention
from app.modules.spare_parts_requests.models import SparePartRequest, SparePartRequestItem
from app.modules.users.models import User
from web import main


@pytest.fixture()
def repair_page(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False)
    with TestingSession() as db:
        user = User(
            username="repair-completion-tester",
            full_name="مختبر حالة الإصلاح",
            hashed_password=hash_password("Test@12345"),
            role="admin",
        )
        db.add(user)
        equipment_type = EquipmentType(name="نوع اختبار إكمال الإصلاح", measurement_unit="km")
        db.add(equipment_type)
        db.flush()
        equipment_model = EquipmentModel(
            name="طراز اختبار إكمال الإصلاح", equipment_type_id=equipment_type.id
        )
        db.add(equipment_model)
        db.flush()
        equipment = Equipment(
            asset_code="REPAIR-COMPLETE-TEST",
            equipment_type_id=equipment_type.id,
            equipment_model_id=equipment_model.id,
            technical_condition="ready",
            operational_status="available",
        )
        db.add(equipment)
        db.flush()
        fault = Fault(
            equipment_id=equipment.id,
            reported_date=date.today(),
            fault_type="عطل اختبار",
            description="عطل لاختبار إكمال الإصلاح",
            severity="medium",
            status="repairing",
            exploitation_impact="limited",
        )
        db.add(fault)
        db.flush()
        repair = Repair(
            fault_id=fault.id,
            repair_date=date.today(),
            repair_start_date=date.today(),
            action_taken="فحص أولي",
            workshop_type="internal",
            status="in_progress",
        )
        db.add(repair)
        db.flush()
        request = SparePartRequest(
            request_number="SPR-REPAIR-COMPLETE-TEST",
            request_date=date.today(),
            source_type="repair",
            repair_id=repair.id,
            equipment_id=equipment.id,
            status="pending",
            requested_by_id=user.id,
        )
        db.add(request)
        db.flush()
        item = SparePartRequestItem(
            request_id=request.id,
            part_name="قطعة اختبار",
            requested_quantity=2,
            received_quantity=0,
        )
        db.add(item)
        db.commit()
        ids = {"user": user.id, "fault": fault.id, "repair": repair.id, "request": request.id, "item": item.id}

    def override_get_db():
        with TestingSession() as session:
            yield session

    monkeypatch.setattr(main, "init_db", lambda: None)
    monkeypatch.setattr(main, "create_default_admin", lambda: None)
    monkeypatch.setattr(session_module, "SessionLocal", TestingSession)
    app = main.create_app()
    app.dependency_overrides[session_module.get_db] = override_get_db
    try:
        with TestClient(app) as client:
            login = client.post(
                "/login",
                data={"username": "repair-completion-tester", "password": "Test@12345"},
                follow_redirects=False,
            )
            assert login.status_code in (302, 303), login.text
            yield client, TestingSession, ids
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_end_date_updates_persisted_statuses_and_fault_table(repair_page):
    client, TestingSession, ids = repair_page
    response = client.patch(
        f"/api/faults-repairs/repairs/{ids['repair']}",
        json={
            "repair_start_date": date.today().isoformat(),
            "repair_end_date": date.today().isoformat(),
            "action_taken": "إصلاح مكتمل للاختبار",
            "workshop_type": "internal",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"

    with TestingSession() as db:
        repair = db.get(Repair, ids["repair"])
        fault = db.get(Fault, ids["fault"])
        request = db.get(SparePartRequest, ids["request"])
        item = db.get(SparePartRequestItem, ids["item"])
        assert (repair.status, repair.repair_end_date) == ("completed", date.today())
        assert fault.status == "repaired"
        assert (request.status, item.requested_quantity, item.received_quantity) == (
            "pending", 2, 0
        )

    body = client.get("/faults-repairs/faults").text
    assert re.search(
        r'<tr data-status="repaired">.*?<span class="state">تم الإصلاح</span>',
        body,
        re.S,
    ), "سجل الأعطال لا يعرض الحالة المحفوظة بعد إعادة تحميل الصفحة"
    assert "SPR-REPAIR-COMPLETE-TEST" in body
    assert "معلق" in body


def test_repair_detail_edits_and_persists_fields_for_any_record(repair_page):
    client, TestingSession, ids = repair_page
    with TestingSession() as db:
        other = Repair(
            fault_id=ids["fault"], repair_date=date.today(),
            repair_start_date=date.today(), repair_end_date=date.today(),
            action_taken="سجل آخر مستقل", workshop_type="internal", status="completed",
        )
        db.add(other)
        db.commit()
        other_id = other.id
    page = client.get(f"/faults-repairs/repairs/{ids['repair']}")
    assert page.status_code == 200
    assert 'id="editRepair"' in page.text
    assert 'id="saveRepair"' in page.text
    assert 'id="cancelRepair"' in page.text
    assert '<form id="repairForm" data-em-root>' in page.text
    assert 'data-em-action="save"' in page.text
    assert "send('/api/faults-repairs/repairs/" in page.text
    assert "','PATCH',d,msg)" in page.text
    assert "if(window.EditManager)EditManager.reset();" in page.text
    template = Path("app/modules/faults_repairs/templates/repair_detail.html").read_text(encoding="utf-8")
    assert 'class="interventionEdit rd-grid" data-id="{{ intervention.id }}" data-em-root' in template
    assert 'id="interventionForm" class="rd-grid" style="margin-top:12px" data-em-root' in template
    assert "['meter_value','labor_hours','repair_end_date']" in page.text
    assert "if(d[k]==='')d[k]=null" in page.text

    response = client.patch(
        f"/api/faults-repairs/repairs/{ids['repair']}",
        json={
            "repair_start_date": date.today().isoformat(),
            "repair_end_date": None,
            "action_taken": "تم تعديل الإجراء",
            "technician": "فني الاختبار",
            "workshop_type": "internal",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["action_taken"] == "تم تعديل الإجراء"

    reloaded = client.get(f"/faults-repairs/repairs/{ids['repair']}")
    assert "تم تعديل الإجراء" in reloaded.text
    assert "تم حفظ التعديلات بنجاح" in client.get(
        f"/faults-repairs/repairs/{ids['repair']}?saved=1"
    ).text
    with TestingSession() as db:
        repair = db.get(Repair, ids["repair"])
        assert repair.action_taken == "تم تعديل الإجراء"
        assert repair.technician == "فني الاختبار"
        assert repair.status == "in_progress"
        assert db.get(Repair, other_id).action_taken == "سجل آخر مستقل"


def test_repair_update_rejects_invalid_dates_without_changing_saved_values(repair_page):
    client, TestingSession, ids = repair_page
    response = client.patch(
        f"/api/faults-repairs/repairs/{ids['repair']}",
        json={
            "repair_start_date": date.today().isoformat(),
            "repair_end_date": date(2000, 1, 1).isoformat(),
            "action_taken": "يجب ألا تحفظ",
            "workshop_type": "internal",
        },
    )
    assert response.status_code == 422
    assert "يسبق" in response.text
    with TestingSession() as db:
        repair = db.get(Repair, ids["repair"])
        assert repair.action_taken == "فحص أولي"
        assert repair.repair_end_date is None


def test_intervention_delete_preview_warns_but_allows_historical_delete(repair_page):
    client, TestingSession, ids = repair_page
    technician = client.post("/api/faults-repairs/technicians", json={
        "employee_number": "TECH-DELETE-PREVIEW",
        "full_name": "فني معاينة",
    })
    assert technician.status_code == 201, technician.text
    intervention = client.post("/api/faults-repairs/technician-interventions", json={
        "repair_id": ids["repair"],
        "technician_id": technician.json()["id"],
        "intervention_date": date.today().isoformat(),
        "hours": 2.5,
        "work_description": "فحص",
    })
    assert intervention.status_code == 201, intervention.text
    intervention_id = intervention.json()["id"]

    preview = client.get(f"/api/faults-repairs/technician-interventions/{intervention_id}/delete-impact")
    assert preview.status_code == 200, preview.text
    data = preview.json()
    assert "فني معاينة" in data["label"] and "2.5" in data["label"]
    assert any(row.get("kind") == "recalculate" for row in data["effects"])
    assert data.get("blocked") is None
    assert "MaterielDeleteImpact.confirmOne" in client.get(f"/faults-repairs/repairs/{ids['repair']}").text

    with TestingSession() as db:
        db.get(Repair, ids["repair"]).status = "completed"
        db.commit()
    blocked = client.get(f"/api/faults-repairs/technician-interventions/{intervention_id}/delete-impact")
    assert blocked.status_code == 200
    assert blocked.json().get("blocked") is None
    assert any(row.get("kind") == "warning" and "إصلاح تاريخي" in row["label"] for row in blocked.json()["effects"])
    deleted = client.delete(f"/api/faults-repairs/technician-interventions/{intervention_id}")
    assert deleted.status_code == 204
    with TestingSession() as db:
        assert db.get(TechnicianIntervention, intervention_id) is None


def test_repair_update_can_clear_action_and_change_workshop(repair_page):
    client, TestingSession, ids = repair_page
    response = client.patch(
        f"/api/faults-repairs/repairs/{ids['repair']}",
        json={
            "repair_start_date": date.today().isoformat(),
            "repair_end_date": None,
            "action_taken": "",
            "workshop_type": "internal",
            "workshop": "الورشة الجديدة",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["action_taken"] == ""
    assert response.json()["workshop"] == "الورشة الجديدة"
    with TestingSession() as db:
        repair = db.get(Repair, ids["repair"])
        assert repair.action_taken == ""
        assert repair.workshop == "الورشة الجديدة"


def test_historical_repair_detail_remains_editable(repair_page):
    client, TestingSession, ids = repair_page
    with TestingSession() as db:
        repair = db.get(Repair, ids["repair"])
        repair.status = "completed"
        repair.repair_end_date = date.today()
        db.get(Fault, ids["fault"]).status = "repaired"
        db.commit()

    page = client.get(f"/faults-repairs/repairs/{ids['repair']}")
    assert page.status_code == 200
    assert 'id="editRepair"' in page.text
    response = client.patch(
        f"/api/faults-repairs/repairs/{ids['repair']}",
        json={
            "repair_start_date": date.today().isoformat(),
            "repair_end_date": date.today().isoformat(),
            "action_taken": "تصحيح سجل تاريخي",
            "workshop_type": "internal",
        },
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "completed"
    with TestingSession() as db:
        assert db.get(Repair, ids["repair"]).action_taken == "تصحيح سجل تاريخي"
