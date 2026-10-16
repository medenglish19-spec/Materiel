from datetime import date, datetime, timedelta
from pathlib import Path
import re
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import model_registry  # noqa: F401
from app.database.base import Base
from app.modules.dashboard import router as dashboard_router
from app.modules.equipment.models import Equipment
from app.modules.equipment_types.models import EquipmentType
from app.modules.faults_repairs import services as repair_services
from app.modules.faults_repairs.models import Fault, Repair
from app.modules.missions import services as mission_services
from app.modules.missions.models import Mission
from app.modules.spare_parts_requests import services as request_services
from app.modules.spare_parts_requests.schemas import (
    SparePartRequestCreate,
    SparePartRequestItemCreate,
    SparePartRequestItemUpdate,
)


def _metric_values(page):
    return dict(re.findall(r'data-dashboard-metric="([^"]+)">([^<]*)</(?:div|span)>', page))


def test_dashboard_metrics_follow_live_domain_records_after_changes():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False)
    Base.metadata.create_all(engine)
    db = TestingSession()
    equipment_ids = {}
    repair_ids = []
    try:
        kind = EquipmentType(name="Dashboard metric test type", measurement_unit="km")
        db.add(kind)
        db.flush()
        for code, condition in (
            ("DASH-A", "ready"),
            ("DASH-B", "ready"),
            ("DASH-C", "broken"),
            ("DASH-D", "ready"),
            ("DASH-E", "ready"),
            ("DASH-F", "ready_restricted"),
        ):
            item = Equipment(
                asset_code=code,
                equipment_type_id=kind.id,
                technical_condition=condition,
                operational_status="unavailable" if condition == "broken" else "available",
            )
            db.add(item)
            db.flush()
            equipment_ids[code] = item.id

        def add_repair(code, workshop):
            fault = Fault(
                equipment_id=equipment_ids[code],
                reported_date=date.today(),
                description="Dashboard test fault",
                severity="medium",
                status="repairing",
                exploitation_impact="none",
            )
            db.add(fault)
            db.flush()
            repair = Repair(
                fault_id=fault.id,
                repair_date=date.today(),
                repair_start_date=date.today(),
                workshop_type=workshop,
                external_dispatch_document="DISPATCH-1" if workshop == "external" else None,
                action_taken="Inspection",
                status="in_progress",
            )
            db.add(repair)
            db.flush()
            repair_ids.append(repair.id)
            return fault

        fault_a = add_repair("DASH-A", "internal")
        add_repair("DASH-A", "external")  # Same equipment must count once; external wins.
        add_repair("DASH-E", "internal")
        db.commit()

        mission = mission_services.add_mission(
            db,
            {
                "equipment_id": equipment_ids["DASH-D"],
                "start_date": date.today() - timedelta(days=1),
                "end_date": None,
            },
        )
        request = request_services.create_request(
            db,
            SparePartRequestCreate(
                request_number="DASH-PENDING-1",
                request_date=date.today(),
                source_type="fault",
                source_id=fault_a.id,
                items=[SparePartRequestItemCreate(part_name="test filter", requested_quantity=1)],
            ),
        )
        mission_id = mission.id
        request_id = request.id
        db.commit()
        db.close()

        app = FastAPI()

        def override_db():
            session = TestingSession()
            try:
                yield session
            finally:
                session.close()

        app.include_router(dashboard_router.router)
        app.dependency_overrides[dashboard_router.get_db] = override_db
        app.dependency_overrides[dashboard_router.get_current_user] = lambda: SimpleNamespace(
            full_name="Dashboard tester"
        )

        with TestClient(app) as client:
            before = client.get("/dashboard")
            assert before.status_code == 200
            assert _metric_values(before.text) == {
                "readiness": "66.7%",
                "broken": "1",
                "internal-repairs": "1",
                "external-repairs": "1",
                "missions": "1",
                "pending-parts": "1",
                "notifications": "0",
            }

            for repair_id in repair_ids:
                session = TestingSession()
                try:
                    repair = session.get(Repair, repair_id)
                    repair_services.change_repair_status(session, repair, "completed")
                finally:
                    session.close()

            verification = TestingSession()
            try:
                assert [verification.get(Repair, repair_id).status for repair_id in repair_ids] == [
                    "completed", "completed", "completed"
                ]
            finally:
                verification.close()

            session = TestingSession()
            try:
                session.get(Mission, mission_id).end_date = date.today() - timedelta(days=1)
                session.commit()
                request = request_services.get_request(session, request_id)
                request_services.update_item(
                    session,
                    request.items[0],
                    SparePartRequestItemUpdate(
                        received_quantity=1,
                        received_date=date.today(),
                        recipient="Receiver",
                        supplier_institution="Supplier",
                    ),
                )
            finally:
                session.close()

            after = client.get("/dashboard")
            assert after.status_code == 200
            assert _metric_values(after.text) == {
                "readiness": "66.7%",
                "broken": "1",
                "internal-repairs": "0",
                "external-repairs": "0",
                "missions": "0",
                "pending-parts": "0",
                "notifications": "0",
            }
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_faults_repairs_dashboard_counts_repairs_separately_by_status():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()
    try:
        equipment_type = EquipmentType(name="Repair status test type", measurement_unit="km")
        session.add(equipment_type)
        session.flush()
        equipment = Equipment(
            asset_code="REPAIR-STATUS-1",
            equipment_type_id=equipment_type.id,
            technical_condition="ready",
            operational_status="available",
        )
        session.add(equipment)
        session.flush()

        for index, status in enumerate(("in_progress", "completed", "cancelled")):
            fault = Fault(
                equipment_id=equipment.id,
                reported_date=date.today(),
                description=f"Repair status test fault {index}",
                severity="medium",
                status="repairing",
                exploitation_impact="none",
            )
            session.add(fault)
            session.flush()
            session.add(
                Repair(
                    fault_id=fault.id,
                    repair_date=date.today(),
                    action_taken="Repair status test",
                    workshop_type="internal",
                    status=status,
                )
            )
        session.commit()

        stats = repair_services.dashboard_stats(session)

        assert stats["repairs_total"] == 3
        assert stats["repairs_by_status"] == {
            "in_progress": 1,
            "completed": 1,
            "cancelled": 1,
        }
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_dashboard_readiness_is_zero_for_an_empty_fleet():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False)
    Base.metadata.create_all(engine)
    app = FastAPI()

    def override_db():
        session = TestingSession()
        try:
            yield session
        finally:
            session.close()

    app.include_router(dashboard_router.router)
    app.dependency_overrides[dashboard_router.get_db] = override_db
    app.dependency_overrides[dashboard_router.get_current_user] = lambda: SimpleNamespace(
        full_name="Dashboard tester"
    )
    try:
        with TestClient(app) as client:
            response = client.get("/dashboard")
            assert response.status_code == 200
            assert _metric_values(response.text)["readiness"] == "0.0%"
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_due_tire_battery_and_notification_counts_follow_install_and_removal(monkeypatch):
    from app.modules.batteries import services as battery_services
    from app.modules.equipment_types.models import EquipmentModel
    from app.modules.tires import services as tire_services
    from app.modules.tires.models import TirePosition

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False)
    Base.metadata.create_all(engine)
    db = TestingSession()
    try:
        kind = EquipmentType(name="Dashboard due test type", measurement_unit="km")
        db.add(kind)
        db.flush()
        model = EquipmentModel(
            name="Dashboard due test model",
            equipment_type_id=kind.id,
            has_tires=True,
            tire_positions_required=4,
            tire_size="205/55",
            has_batteries=True,
            battery_count_required=1,
        )
        db.add(model)
        db.flush()
        equipment = Equipment(
            asset_code="DASH-DUE-1",
            equipment_type_id=kind.id,
            equipment_model_id=model.id,
            technical_condition="ready",
            operational_status="available",
        )
        position = TirePosition(
            code="DASH-POS-1",
            name="Position 1",
            equipment_model_id=model.id,
            sort_order=1,
        )
        db.add_all([equipment, position])
        db.commit()
        equipment_id, position_id = equipment.id, position.id
        db.close()

        session = TestingSession()
        tire = tire_services.add_tire(
            session,
            {"serial_number": "DASH-TIRE-1", "size": "205/55", "expiry_date": date.today()},
        )
        tire_services.add_movement(
            session,
            tire.id,
            {
                "movement_type": "install",
                "movement_date": date.today(),
                "movement_datetime": datetime.now() - timedelta(seconds=3),
                "equipment_id": equipment_id,
                "position_id": position_id,
            },
        )
        battery = battery_services.add_battery(
            session,
            {
                "serial_number": "DASH-BATTERY-1",
                "receipt_date": date.today() - timedelta(days=365 * 3),
            },
        )
        battery_services.add_movement(
            session,
            battery.id,
            {"movement_type": "install", "movement_date": date.today(), "equipment_id": equipment_id},
        )
        tire_id, battery_id = tire.id, battery.id
        session.close()

        class Tomorrow(date):
            @classmethod
            def today(cls):
                return date.today() + timedelta(days=1)

        monkeypatch.setattr(tire_services, "date", Tomorrow)
        app = FastAPI()

        def override_db():
            request_session = TestingSession()
            try:
                yield request_session
            finally:
                request_session.close()

        app.include_router(dashboard_router.router)
        app.dependency_overrides[dashboard_router.get_db] = override_db
        app.dependency_overrides[dashboard_router.get_current_user] = lambda: SimpleNamespace(
            full_name="Dashboard tester"
        )

        with TestClient(app) as client:
            before = client.get("/dashboard")
            assert before.status_code == 200
            assert _metric_values(before.text)["notifications"] == "2"
            assert "DASH-TIRE-1" in before.text and before.text.count("DASH-TIRE-1") == 1
            assert "DASH-BATTERY-1" in before.text and before.text.count("DASH-BATTERY-1") == 1
            assert "data-dashboard-metric=\"due-tires\"" not in before.text
            assert "data-dashboard-metric=\"due-batteries\"" not in before.text
            assert "الإطارات المركبة المستحقة للاستبدال</h2>" not in before.text
            assert "البطاريات المركبة التي حان موعد استبدالها</h2>" not in before.text

            session = TestingSession()
            try:
                now = datetime.now()
                tire_services.add_movement(
                    session,
                    tire_id,
                    {
                        "movement_type": "remove",
                        "movement_date": date.today(),
                        "movement_datetime": now - timedelta(seconds=1),
                        "reason": "replacement",
                            "removal_disposition": "stock",
                    },
                )
                battery_services.add_movement(
                    session,
                    battery_id,
                    {"movement_type": "remove", "movement_date": date.today(), "reason": "replacement"},
                )
            finally:
                session.close()

            after = client.get("/dashboard")
            assert after.status_code == 200
            assert _metric_values(after.text)["notifications"] == "0"
            assert "DASH-TIRE-1" not in after.text and "DASH-BATTERY-1" not in after.text
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()
