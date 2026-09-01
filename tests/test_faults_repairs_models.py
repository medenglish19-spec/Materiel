from sqlalchemy import CheckConstraint
from app.modules.faults_repairs.models import Fault, Repair, RepairPart, SparePart, Technician, TechnicianIntervention


def test_fault_repair_part_model_contracts():
    assert Fault.__tablename__ == "faults"
    assert Repair.__tablename__ == "repairs"
    assert SparePart.__tablename__ == "spare_parts"
    assert RepairPart.__tablename__ == "repair_parts"

    assert "equipment_id" in Fault.__table__.columns
    assert "maintenance_record_id" in Fault.__table__.columns
    assert "fault_id" in Repair.__table__.columns
    assert "spare_part_id" in RepairPart.__table__.columns
    assert "quantity" in RepairPart.__table__.columns


def test_fault_statuses_are_explicit():
    checks = {c.name: str(c.sqltext) for c in Fault.__table__.constraints if c.name}
    assert "ck_fault_status" in checks
    assert "waiting_parts" in checks["ck_fault_status"]
    assert "ck_fault_severity" in checks


def test_repair_part_quantity_must_be_positive():
    checks = {c.name: str(c.sqltext) for c in RepairPart.__table__.constraints if isinstance(c, CheckConstraint) and c.name}
    assert checks["ck_repair_part_quantity_positive"] == "quantity > 0"


def test_spare_part_has_receiving_document_only():
    assert "receiving_document" in SparePart.__table__.columns
    assert "unit" not in SparePart.__table__.columns
    assert "is_active" not in SparePart.__table__.columns


def test_repair_part_requires_distribution_document():
    assert "distribution_document" in RepairPart.__table__.columns
    assert RepairPart.__table__.columns["distribution_document"].nullable is False


def test_technician_contracts():
    assert Technician.__tablename__ == "workshop_technicians"
    assert TechnicianIntervention.__tablename__ == "technician_interventions"
    assert "employee_number" in Technician.__table__.columns
    assert "specialization" in Technician.__table__.columns
    assert "technician_id" in TechnicianIntervention.__table__.columns
    assert "hours" in TechnicianIntervention.__table__.columns
    assert "work_description" in TechnicianIntervention.__table__.columns
