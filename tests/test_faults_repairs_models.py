from app.modules.faults_repairs.models import Fault, Repair, RepairPart, SparePart


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
    checks = {c.name: str(c.sqltext) for c in RepairPart.__table__.constraints if c.name}
    assert checks["ck_repair_part_quantity_positive"] == "quantity > 0"
