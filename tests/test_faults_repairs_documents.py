from app.modules.faults_repairs.models import Fault, Repair


def test_fault_has_report_number_and_note():
    assert "report_number" in Fault.__table__.columns
    assert "note" in Fault.__table__.columns


def test_repair_has_workshop_and_document_controls():
    assert "workshop_type" in Repair.__table__.columns
    assert "repair_document" in Repair.__table__.columns
    assert "external_dispatch_document" in Repair.__table__.columns

    checks = {c.name: str(c.sqltext) for c in Repair.__table__.constraints if c.name}
    assert "ck_repair_workshop_type" in checks
    assert "ck_external_repair_requires_dispatch_document" in checks
    assert "external_dispatch_document IS NOT NULL" in checks["ck_external_repair_requires_dispatch_document"]
