from datetime import date
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.database import model_registry  # noqa: F401
from app.database.base import Base
from scripts.seed_test_data import MARKER, clean, seed


def _engine(path: Path):
    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    @event.listens_for(engine, "connect")
    def _fk(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()
    Base.metadata.create_all(engine)
    return engine


def test_seed_builds_a_complete_linked_dataset_and_clean_removes_only_it(tmp_path):
    engine = _engine(tmp_path / "seed.db")
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = SessionLocal()
    try:
        summary = seed(db)
        assert summary == {
            "marker": MARKER,
            "categories": 3,
            "types": 3,
            "models": 3,
            "equipment": 9,
            "technicians": 3,
            "drivers": 3,
            "tires": 21,
            "batteries": 12,
            "maintenance_records": 9,
            "faults": 3,
            "repairs": 3,
            "spare_requests": 3,
            "distribution_documents": 3,
            "return_documents": 1,
            "meter_readings": 18,
        }

        from app.modules.equipment.models import Equipment
        from app.modules.equipment_types.models import EquipmentType
        from app.modules.faults_repairs.models import Fault, Repair, Technician
        from app.modules.maintenance.models import MaintenanceRecord
        from app.modules.meter_readings.models import MeterReading
        from app.modules.spare_parts_movements import services as movement_services
        from app.modules.spare_parts_movements.models import SparePartMovementDocument
        from app.modules.spare_parts_requests.models import SparePartRequest
        from app.modules.tires import services as tire_services
        from app.modules.tires.models import Tire
        from app.modules.batteries import services as battery_services
        from app.modules.batteries.models import Battery

        equipment = db.query(Equipment).filter(Equipment.asset_code.like(f"{MARKER}%")).order_by(Equipment.id).all()
        assert len(equipment) == 9
        hours_types = {e.equipment_type_id for e in equipment[3:6]}
        km_types = {e.equipment_type_id for e in equipment[:3] + equipment[6:]}
        assert len(hours_types) == 1
        assert len(km_types) == 2
        assert all(e.current_hours is not None for e in equipment[3:6])

        technicians = db.query(Technician).filter(Technician.employee_number.like(f"{MARKER}%")).all()
        assert {t.full_name for t in technicians} == {"أحمد بن صالح", "محمد قادري", "سمير بوزيد"}

        repairs = db.query(Repair).filter(Repair.repair_document.like(f"{MARKER}%")).all()
        assert len(repairs) == 3
        assert any(r.workshop_type == "external" for r in repairs)
        assert any(r.workshop_type == "internal" for r in repairs)

        records = db.query(MaintenanceRecord).filter(MaintenanceRecord.work_order.like(f"{MARKER}%")).all()
        assert len(records) == 9
        assert all(r.operation_id and r.plan_id for r in records)

        requests = db.query(SparePartRequest).filter(SparePartRequest.request_number.like(f"{MARKER}%")).all()
        assert len(requests) == 3
        assert all(r.status == "pending" for r in requests)
        assert all(r.items[0].received_quantity == 3 for r in requests)
        assert all(r.items[0].supplier_institution.endswith(MARKER) for r in requests)

        distributions = db.query(SparePartMovementDocument).filter(
            SparePartMovementDocument.document_number.like(f"{MARKER}-DIST-%")
        ).all()
        returns = db.query(SparePartMovementDocument).filter(
            SparePartMovementDocument.document_number.like(f"{MARKER}-RETURN-%")
        ).all()
        assert len(distributions) == 3
        assert len(returns) == 1

        first_item = requests[0].items[0]
        available = movement_services.available_quantity(db, first_item)
        assert available == 1
        assert returns[0].recipient == first_item.supplier_institution
        assert returns[0].items[0].received_request_item_id == first_item.id
        assert returns[0].items[0].source_item_id is None
        assert returns[0].items[0].quantity == 1

        tires = db.query(Tire).filter(Tire.serial_number.like(f"{MARKER}%")).all()
        installed_tires = [t for t in tires if tire_services.current_state(db, t.id).get("installed")]
        assert len(installed_tires) == 18

        batteries = db.query(Battery).filter(Battery.serial_number.like(f"{MARKER}%")).all()
        installed_batteries = [b for b in batteries if battery_services.current_state(db, b.id).get("installed")]
        assert len(installed_batteries) == 9

        readings = db.query(MeterReading).filter(MeterReading.source == f"{MARKER}-meter").all()
        assert len(readings) == 18
        assert any(r.hours is not None for r in readings)
        assert any(r.odometer is not None for r in readings)

        # Prove the seed is explicitly removable and the second seed cannot
        # silently overwrite or duplicate the first one.
        try:
            seed(db)
        except RuntimeError as exc:
            assert "نفّذ clean أولًا" in str(exc)
        else:
            raise AssertionError("seed must refuse to duplicate its own namespace")

        result = clean(db)
        assert result["deleted"] == 1
        assert db.query(Equipment).filter(Equipment.asset_code.like(f"{MARKER}%")).count() == 0
        assert db.query(SparePartRequest).filter(SparePartRequest.request_number.like(f"{MARKER}%")).count() == 0
        assert db.query(SparePartMovementDocument).filter(SparePartMovementDocument.document_number.like(f"{MARKER}%")).count() == 0
    finally:
        db.close()
        engine.dispose()
